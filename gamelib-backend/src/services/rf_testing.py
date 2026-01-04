"""
Test and evaluate the trained global RF model.

This script loads the trained rf_model_global.pkl and evaluates its performance
on real user data from users_db.csv.
"""

import json
from pathlib import Path
from typing import cast
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from scipy import sparse
import pandas as pd

from rf_model import (
    _load_games_df,
    _load_vectorizer,
    _build_feature_matrix,
    _load_users_csv,
    _aggregate_user_targets,
    RandomForestScorer,
    MODEL_DIR,
)


def evaluate_model_performance():
    """Load trained global model and evaluate on test data."""
    print("="*70)
    print("GLOBAL RF MODEL EVALUATION")
    print("="*70)
    
    # Load trained model
    print("\n[1/5] Loading trained global model...")
    model_path = MODEL_DIR / "rf_model_global.pkl"
    if not model_path.exists():
        print(f"ERROR: Trained model not found at {model_path}")
        print("Please train the model first by running: python rf_model.py")
        return
    
    scorer = RandomForestScorer(model_path=model_path)
    if not scorer.is_trained:
        print("ERROR: Model failed to load")
        return
    print(f"✓ Model loaded successfully")
    print(f"  Feature matrix shape: {scorer.feature_matrix.shape}")
    
    # Load user data
    print("\n[2/5] Loading user data from users_db.csv...")
    users_df = _load_users_csv()
    print(f"✓ Loaded {len(users_df):,} user-game records")
    
    # Aggregate targets
    print("\n[3/5] Aggregating user targets (min_users=5)...")
    targets = _aggregate_user_targets(users_df, min_users=5)
    print(f"✓ Aggregated {len(targets):,} games with sufficient user data")
    
    # Prepare test data
    print("\n[4/5] Preparing test dataset...")
    mask = scorer.games_df["game_id"].isin(targets.keys())
    if not mask.any():
        print("ERROR: No overlapping games between model and user data")
        return
    
    rows = np.where(np.asarray(mask.values, dtype=bool))[0]
    X_all = scorer.feature_matrix[rows]
    y_all = np.array([targets[int(gid)] for gid in scorer.games_df.loc[mask, "game_id"]])
    game_ids_test = scorer.games_df.loc[mask, "game_id"].tolist()
    
    print(f"✓ Test set prepared: {X_all.shape[0]:,} games")
    
    # Split into train/test for evaluation
    X_train, X_test, y_train, y_test, gids_train, gids_test = train_test_split(
        X_all, y_all, game_ids_test, test_size=0.2, random_state=42
    )
    
    print(f"  Train set: {X_train.shape[0]:,} games")
    print(f"  Test set:  {X_test.shape[0]:,} games")
    
    # Evaluate model
    print("\n[5/5] Evaluating model performance...")
    if scorer.model is None:
        print("ERROR: Model is None, cannot evaluate")
        return
    
    train_pred = scorer.model.predict(X_train)
    test_pred = scorer.model.predict(X_test)
    
    # Calculate metrics
    train_rmse = float(np.sqrt(mean_squared_error(y_train, train_pred)))
    test_rmse = float(np.sqrt(mean_squared_error(y_test, test_pred)))
    train_mae = float(mean_absolute_error(y_train, train_pred))
    test_mae = float(mean_absolute_error(y_test, test_pred))
    train_r2 = float(r2_score(y_train, train_pred))
    test_r2 = float(r2_score(y_test, test_pred))
    
    print("\n" + "="*70)
    print("EVALUATION RESULTS")
    print("="*70)
    
    print("\nMetrics (lower is better for RMSE/MAE, higher is better for R²):")
    print(f"\n  {'Metric':<20} {'Train':<15} {'Test':<15} {'Difference':<15}")
    print(f"  {'-'*20} {'-'*15} {'-'*15} {'-'*15}")
    print(f"  {'RMSE':<20} {train_rmse:<15.2f} {test_rmse:<15.2f} {abs(test_rmse - train_rmse):<15.2f}")
    print(f"  {'MAE':<20} {train_mae:<15.2f} {test_mae:<15.2f} {abs(test_mae - train_mae):<15.2f}")
    print(f"  {'R² Score':<20} {train_r2:<15.4f} {test_r2:<15.4f} {abs(test_r2 - train_r2):<15.4f}")
    
    # Prediction distribution
    print("\nPrediction Statistics:")
    print(f"  Target (actual) range:     [{y_test.min():.1f}, {y_test.max():.1f}]")
    print(f"  Prediction range:          [{test_pred.min():.1f}, {test_pred.max():.1f}]")
    print(f"  Target mean:               {y_test.mean():.1f}")
    print(f"  Prediction mean:           {test_pred.mean():.1f}")
    
    # Sample predictions
    print("\nSample Predictions (10 random games):")
    print(f"  {'Game ID':<12} {'Actual':<12} {'Predicted':<12} {'Error':<12}")
    print(f"  {'-'*12} {'-'*12} {'-'*12} {'-'*12}")
    sample_indices = np.random.choice(len(test_pred), min(10, len(test_pred)), replace=False)
    for idx in sample_indices:
        gid = gids_test[idx]
        actual = y_test[idx]
        pred = test_pred[idx]
        error = abs(actual - pred)
        print(f"  {gid:<12} {actual:<12.1f} {pred:<12.1f} {error:<12.1f}")
    
    # Overfitting check
    print("\nOverfitting Analysis:")
    if abs(test_rmse - train_rmse) < train_rmse * 0.1:
        print("  ✓ Model generalizes well (test RMSE similar to train RMSE)")
    elif test_rmse > train_rmse * 1.2:
        print("  ⚠ Possible overfitting (test RMSE significantly higher than train)")
    else:
        print("  ℹ Model shows some overfitting but within acceptable range")
    
    print("\n" + "="*70)
    
    # Save results
    results = {
        "train_metrics": {
            "rmse": train_rmse,
            "mae": train_mae,
            "r2": train_r2,
        },
        "test_metrics": {
            "rmse": test_rmse,
            "mae": test_mae,
            "r2": test_r2,
        },
        "dataset_info": {
            "total_games": int(X_all.shape[0]),
            "train_games": int(X_train.shape[0]),
            "test_games": int(X_test.shape[0]),
        }
    }
    
    results_path = Path("rf_evaluation_results.json")
    results_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to: {results_path.absolute()}")


if __name__ == "__main__":
    evaluate_model_performance()
