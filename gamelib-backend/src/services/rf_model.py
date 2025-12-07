"""
Random Forest scoring for personalized game recommendations.

This module trains a RandomForestRegressor on a user's owned games, using
features derived from games_db.csv and the existing TF-IDF vectorizer.
It then scores candidate games to re-rank recommendations.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import MultiLabelBinarizer
from sklearn.metrics import mean_squared_error
import joblib


__all__ = [
	"RandomForestScorer",
	"train_and_score",
	"_load_games_df",
	"_load_vectorizer",
	"_load_users_csv",
	"_build_feature_matrix",
	"_build_user_targets",
	"_aggregate_user_targets",
	"MODEL_DIR",
	"SERVICES_DIR",
]


SERVICES_DIR = Path(__file__).resolve().parent
CSV_PATH = SERVICES_DIR.parent / "db" / "repositories" / "games_db.csv"
USERS_CSV_PATH = SERVICES_DIR.parent / "db" / "repositories" / "users_db.csv"
VECTORIZER_PATH = SERVICES_DIR / "tfidf_vectorizer.pkl"
MODEL_DIR = SERVICES_DIR


def _load_games_df() -> pd.DataFrame:
	if not CSV_PATH.exists():
		raise FileNotFoundError(f"games_db.csv not found at {CSV_PATH}")
	df = pd.read_csv(CSV_PATH)

	# Ensure expected columns
	for col in ["short_desc", "tags", "genres", "categories", "developers", "publishers", "languages", "platforms"]:
		if col not in df.columns:
			df[col] = ""

	# Basic cleaning
	df["price_usd"] = pd.to_numeric(
		df.get("price_usd", pd.Series(dtype=float)), errors="coerce"
	).fillna(0.0)
	df["positive"] = pd.to_numeric(
		df.get("positive", pd.Series(dtype=float)), errors="coerce"
	).fillna(0).astype(int)
	df["negative"] = pd.to_numeric(
		df.get("negative", pd.Series(dtype=float)), errors="coerce"
	).fillna(0).astype(int)
	df["required_age"] = pd.to_numeric(
		df.get("required_age", pd.Series(dtype=float)), errors="coerce"
	).fillna(0).astype(int)
	df["is_free"] = pd.Series(df.get("is_free", pd.Series(dtype=bool)), dtype=bool).fillna(False).astype(bool)
	df["release_year"] = pd.to_datetime(
		df.get("release_date", pd.Series(dtype="datetime64[ns]")), errors="coerce"
	).dt.year.fillna(0).astype(int)

	# Parse list-like fields
	def split_pipes(val: str) -> List[str]:
		if pd.isna(val) or val is None:
			return []
		return [p.strip() for p in str(val).split("|") if p.strip()]

	for col in ["tags", "genres", "categories", "developers", "publishers", "languages", "platforms"]:
		df[f"{col}_list"] = df[col].apply(split_pipes)

	return df


def _load_vectorizer():
	if not VECTORIZER_PATH.exists():
		return None
	try:
		return joblib.load(VECTORIZER_PATH)
	except Exception:
		return None


def _load_users_csv() -> pd.DataFrame:
	"""Load users_db.csv with columns: steam_id, game_id, playtime_forever, playtime_2weeks, rtime_last_played, name, playtime_score."""
	if not USERS_CSV_PATH.exists():
		raise FileNotFoundError(f"users_db.csv not found at {USERS_CSV_PATH}")
	return pd.read_csv(USERS_CSV_PATH)


def _build_feature_matrix(df: pd.DataFrame, vectorizer) -> Tuple[sparse.csr_matrix, List[int]]:
	# Text features (short_desc). If vectorizer missing, fall back to bag-of-words fit on short_desc.
	desc_corpus = df["short_desc"].fillna("").astype(str).tolist()
	if vectorizer is None:
		from sklearn.feature_extraction.text import TfidfVectorizer
		vectorizer = TfidfVectorizer(max_features=5000, stop_words="english")
		desc_tfidf = vectorizer.fit_transform(desc_corpus)
	else:
		desc_tfidf = vectorizer.transform(desc_corpus)

	# Multi-label categorical encodings
	mlb_fields = ["tags_list", "genres_list", "categories_list", "developers_list", "publishers_list", "languages_list", "platforms_list"]
	mlb_encoders = {}
	mlb_mats = []
	for field in mlb_fields:
		mlb = MultiLabelBinarizer(sparse_output=True)
		mat = mlb.fit_transform(df[field])
		mlb_encoders[field] = mlb
		mlb_mats.append(mat)

	# Numeric features (coerce to float to avoid object dtype in sparse matrices)
	numeric_cols = ["price_usd", "positive", "negative", "required_age", "is_free", "release_year"]
	numeric_frame = df[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
	numeric_mat = sparse.csr_matrix(numeric_frame.values.astype(np.float64))

	feature_matrix = sparse.hstack([desc_tfidf] + mlb_mats + [numeric_mat], format="csr")
	feature_matrix = sparse.csr_matrix(feature_matrix)
	return feature_matrix, df["game_id"].astype(int).tolist()


def _build_user_targets(user_games: Dict[str, Dict[str, float]]) -> Dict[int, float]:
	# playtime_forever is minutes; use log or linear scaling to dampen extremes.
	targets: Dict[int, float] = {}
	for key, payload in user_games.items():
		try:
			gid = int(key)
		except ValueError:
			continue
		playtime = float(payload.get("playtime_forever", 0.0))
		if playtime <= 0:
			continue
		# Log1p to reduce skew, but keep magnitude.
		targets[gid] = np.log1p(playtime) * 100
	return targets


def _aggregate_user_targets(users_df: pd.DataFrame, min_users: int = 5) -> Dict[int, float]:
	"""Aggregate real user playtime data into per-game targets (mean playtime_score across users).
	
	Args:
		users_df: DataFrame from users_db.csv (columns: steam_id, game_id, playtime_score, etc.)
		min_users: Minimum number of users who must own a game for it to be included.
	
	Returns:
		Dict mapping game_id -> mean playtime_score across all users.
	"""
	grouped = users_df.groupby("game_id")["playtime_score"].agg(["mean", "count"]).reset_index()
	grouped = grouped[grouped["count"] >= min_users]
	return dict(zip(grouped["game_id"].astype(int), grouped["mean"].astype(float)))


class RandomForestScorer:
	def __init__(
		self,
		n_estimators: int = 300,
		max_depth: Optional[int] = None,
		random_state: int = 42,
		model_path: Optional[Path] = None,
	):
		self.n_estimators = n_estimators
		self.max_depth = max_depth
		self.random_state = random_state
		self.model_path = model_path or (MODEL_DIR / "rf_model.pkl")
		self.model: Optional[RandomForestRegressor] = None
		self.vectorizer = _load_vectorizer()
		self.games_df = _load_games_df()
		self.feature_matrix, self.game_ids = _build_feature_matrix(self.games_df, self.vectorizer)
		self.is_trained: bool = self._try_load_model()

	def _try_load_model(self) -> bool:
		if not self.model_path.exists():
			return False
		try:
			self.model = joblib.load(self.model_path)
			return True
		except Exception:
			self.model = None
			return False

	def save_model(self):
		if self.model is None:
			return
		try:
			joblib.dump(self.model, self.model_path)
		except Exception as exc:  # pragma: no cover
			print(f"WARNING: failed to save RF model to {self.model_path}: {exc}")

	def _subset_for_user(self, user_targets: Dict[int, float]):
		mask = self.games_df["game_id"].isin(user_targets.keys())
		if not mask.any():
			return None, None, None
		rows = np.where(np.asarray(mask.values, dtype=bool))[0]
		X = self.feature_matrix[rows]
		y = np.array([user_targets[int(gid)] for gid in self.games_df.loc[mask, "game_id"]])
		gids = self.games_df.loc[mask, "game_id"].tolist()
		return X, y, gids

	def train(self, user_games: Dict[str, Dict[str, float]], save: bool = True):
		user_targets = _build_user_targets(user_games)
		X, y, gids = self._subset_for_user(user_targets)
		if X is None or X.shape[0] == 0:
			raise ValueError("No overlapping games between user data and games_db.csv")

		X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.2, random_state=self.random_state)
		
		print(f"  Split: {X_train.shape[0]:,} train / {X_val.shape[0]:,} validation samples")
		print(f"  Fitting Random Forest (this will show tree-by-tree progress)...")
		
		self.model = RandomForestRegressor(
			n_estimators=self.n_estimators,
			max_depth=self.max_depth,
			random_state=self.random_state,
			n_jobs=-1,
			oob_score=False,
			verbose=2  # Show progress for each tree
		)
		self.model.fit(X_train, y_train)
		self.is_trained = True
		if save:
			self.save_model()

		val_pred = self.model.predict(X_val)
		rmse = float(np.sqrt(mean_squared_error(y_val, val_pred)))
		return {"train_samples": int(X_train.shape[0]), "val_samples": int(X_val.shape[0]), "rmse": rmse, "fitted_on_game_ids": gids}

	def score_candidates(self, candidate_game_ids: List[int]) -> List[Tuple[int, float]]:
		if self.model is None:
			raise ValueError("Model not trained. Call train() first.")
		if not candidate_game_ids:
			return []

		mask = self.games_df["game_id"].isin(candidate_game_ids)
		if not mask.any():
			return []
		rows = np.where(np.asarray(mask.values, dtype=bool))[0]
		X_candidates = self.feature_matrix[rows]
		preds = self.model.predict(X_candidates)
		ids = self.games_df.loc[mask, "game_id"].tolist()
		return list(zip(ids, preds))

	def get_feature_explanations(self, game_id: int, top_n: int = 5) -> List[Dict[str, Any]]:
		"""Get simplified feature explanations for why a game scored highly."""
		if self.model is None:
			return []
		
		# Find game in dataframe
		mask = self.games_df["game_id"] == game_id
		if not mask.any():
			return []
		
		game_row = self.games_df[mask].iloc[0]
		explanations = []
		
		# Review score (if high positive reviews)
		if game_row.get("positive", 0) > 1000:
			explanations.append({
				"feature": "Review Score",
				"value": f"{game_row['positive']:,} positive reviews",
				"importance": "high"
			})
		
		# Popular genres
		genres = game_row.get("genres_list", [])
		if genres and len(genres) > 0:
			explanations.append({
				"feature": "Genres",
				"value": ", ".join(genres[:3]),
				"importance": "high"
			})
		
		# Popular tags
		tags = game_row.get("tags_list", [])
		if tags and len(tags) > 0:
			explanations.append({
				"feature": "Tags",
				"value": ", ".join(tags[:3]),
				"importance": "medium"
			})
		
		# Categories (multiplayer, single-player, etc.)
		categories = game_row.get("categories_list", [])
		if categories and len(categories) > 0:
			explanations.append({
				"feature": "Features",
				"value": ", ".join(categories[:3]),
				"importance": "medium"
			})
		
		# Platform availability
		platforms = game_row.get("platforms_list", [])
		if platforms and len(platforms) > 1:
			explanations.append({
				"feature": "Platform Support",
				"value": f"Available on {len(platforms)} platforms",
				"importance": "low"
			})
		
		# Price point
		if game_row.get("is_free", False):
			explanations.append({
				"feature": "Price",
				"value": "Free to Play",
				"importance": "medium"
			})
		elif game_row.get("price_usd", 0) > 0:
			price = game_row["price_usd"]
			if price < 10:
				explanations.append({
					"feature": "Price",
					"value": f"Budget-friendly (${price:.2f})",
					"importance": "low"
				})
		
		return explanations[:top_n]

	def rerank_recommendations(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
		if self.model is None or not recommendations:
			return recommendations
		candidate_ids = [rec.get("game_id") or rec.get("steam_appid") for rec in recommendations]
		candidate_ids = [int(cid) for cid in candidate_ids if cid is not None]
		scored = dict(self.score_candidates(candidate_ids))
		for rec in recommendations:
			gid = rec.get("game_id") or rec.get("steam_appid")
			if gid in scored:
				rec["rf_score"] = float(scored[gid])
				# Add feature explanations
				rec["rf_explanations"] = self.get_feature_explanations(gid, top_n=5)
		return sorted(recommendations, key=lambda r: r.get("rf_score", 0.0), reverse=True)


def train_and_score(user_games_json: str, candidate_game_ids: List[int]) -> Dict[str, Any]:
	user_games = json.loads(user_games_json)
	scorer = RandomForestScorer()
	train_info = scorer.train(user_games)
	scored = scorer.score_candidates(candidate_game_ids)
	return {"train_info": train_info, "scored": scored}


if __name__ == "__main__":
	"""Train a global RF model on aggregated user data from users_db.csv and save it."""
	import sys
	from datetime import datetime
	
	start_time = datetime.now()
	print("="*60)
	print("GLOBAL RF MODEL TRAINING")
	print("="*60)
	
	print(f"[{datetime.now().strftime('%H:%M:%S')}] Loading users_db.csv...")
	users_df = _load_users_csv()
	print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Loaded {len(users_df):,} user-game rows.")
	
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Aggregating user targets (min_users=5)...")
	targets = _aggregate_user_targets(users_df, min_users=5)
	print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Aggregated {len(targets):,} games with sufficient user data.")
	
	# Convert aggregated targets to user_games format for training
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Converting targets to training format...")
	user_games = {str(gid): {"playtime_forever": score / 100.0} for gid, score in targets.items()}
	print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Ready for training")
	
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Initializing RandomForestScorer...")
	print(f"  - Loading games_db.csv...")
	print(f"  - Building feature matrix (TF-IDF + one-hot encodings)...")
	scorer = RandomForestScorer(model_path=MODEL_DIR / "rf_model_global.pkl")
	print(f"[{datetime.now().strftime('%H:%M:%S')}] ✓ Feature matrix ready: {scorer.feature_matrix.shape}")
	
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Training RandomForestRegressor...")
	print(f"  - n_estimators: {scorer.n_estimators}")
	print(f"  - max_depth: {scorer.max_depth}")
	print(f"  - Using all CPU cores (n_jobs=-1)")
	print(f"  - This may take 5-15 minutes depending on data size...")
	print(f"\n{'='*60}")
	
	train_info = scorer.train(user_games, save=True)
	
	print(f"{'='*60}")
	print(f"\n[{datetime.now().strftime('%H:%M:%S')}] ✓ Training complete!")
	print(f"\nTraining Statistics:")
	print(f"  Train samples:      {train_info['train_samples']:,}")
	print(f"  Validation samples: {train_info['val_samples']:,}")
	print(f"  Validation RMSE:    {train_info['rmse']:.2f}")
	print(f"  Games fitted:       {len(train_info['fitted_on_game_ids']):,}")
	
	elapsed = datetime.now() - start_time
	print(f"\nTotal time: {elapsed.total_seconds():.1f}s")
	print(f"\nModel saved to: {scorer.model_path}")
	print("="*60)
