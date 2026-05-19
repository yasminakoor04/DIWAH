import os
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

# Set paths
_SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = _SCRIPT_DIR / "Acc_pipe" / "data" / "processed" / "flirt_reference.csv"
OUTPUT_DIR = _SCRIPT_DIR / "exports" / "feature_plots"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Aesthetic settings for thesis
plt.style.use('seaborn-v0_8-whitegrid')
sns.set_context("paper", font_scale=1.5)

print(f"Loading data from {DATA_PATH}...")
df = pd.read_csv(DATA_PATH, index_col=0)

# Drop any rows where METs is NaN
df = df.dropna(subset=['mets'])

# Select representative FLIRT features for visualization
# We pick a mix of statistical moments, time-domain, and entropy features
features_to_plot = [
    ('reference_acc_x_mean', 'Acc X: Mean (g)'),
    ('reference_acc_x_std', 'Acc X: Std Dev (g)'),
    ('reference_acc_x_skewness', 'Acc X: Skewness'),
    ('reference_acc_x_entropy', 'Acc X: Entropy'),
    ('hr_polar_stat_hr_polar_mean', 'HR: Mean (bpm)'),
    ('hr_polar_stat_hr_polar_std', 'HR: Std Dev (bpm)')
]

# Ensure the columns exist
actual_features = [f for f in features_to_plot if f[0] in df.columns]

if not actual_features:
    print("Error: None of the target features were found in the dataset.")
    exit(1)

print(f"Generating feature distribution plots for {len(actual_features)} features...")

# 1. Feature Distributions Plot
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
axes = axes.flatten()

for idx, (col_name, display_name) in enumerate(actual_features):
    ax = axes[idx]
    
    # Drop NaNs for plotting just this feature
    data_to_plot = df[col_name].dropna()
    
    # Plot histogram with KDE
    sns.histplot(data=data_to_plot, kde=True, ax=ax, color='steelblue', stat='density', alpha=0.6, linewidth=0)
    
    ax.set_title(display_name, fontweight='bold', pad=10)
    ax.set_xlabel('Feature Value')
    ax.set_ylabel('Density')

plt.tight_layout(pad=3.0)
dist_plot_path = OUTPUT_DIR / "flirt_feature_distributions.png"
plt.savefig(dist_plot_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"Saved: {dist_plot_path}")

# 2. Correlation with METs Heatmap
print("Generating correlation heatmap...")
corr_cols = [f[0] for f in actual_features] + ['mets']
corr_display_names = [f[1] for f in actual_features] + ['METs (Ground Truth)']

corr_data = df[corr_cols].dropna()
corr_matrix = corr_data.corr()

plt.figure(figsize=(10, 8))
mask = np.triu(np.ones_like(corr_matrix, dtype=bool))
sns.heatmap(
    corr_matrix, 
    mask=mask,
    annot=True, 
    fmt=".2f", 
    cmap="coolwarm", 
    vmin=-1, 
    vmax=1,
    square=True,
    xticklabels=corr_display_names,
    yticklabels=corr_display_names,
    linewidths=0.5,
    cbar_kws={"shrink": .8}
)
plt.title("Correlation of Extracted FLIRT Features with METs", fontweight='bold', pad=20)
plt.xticks(rotation=45, ha='right')

corr_plot_path = OUTPUT_DIR / "flirt_feature_correlations.png"
plt.savefig(corr_plot_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"Saved: {corr_plot_path}")

# 3. Scatter Plot: Most correlated feature vs METs
print("Generating scatter plot for most correlated feature...")
# Find the feature with highest absolute correlation to METs
corrs = corr_matrix['mets'].drop('mets').abs()
best_feature_col = corrs.idxmax()
best_feature_name = next(f[1] for f in actual_features if f[0] == best_feature_col)

plt.figure(figsize=(8, 6))
sns.scatterplot(
    x=corr_data[best_feature_col], 
    y=corr_data['mets'], 
    alpha=0.4, 
    edgecolor=None,
    color='purple'
)
sns.regplot(
    x=corr_data[best_feature_col], 
    y=corr_data['mets'], 
    scatter=False, 
    color='darkorange',
    line_kws={'linewidth': 2}
)
plt.title(f"METs vs {best_feature_name}", fontweight='bold', pad=15)
plt.xlabel(best_feature_name)
plt.ylabel("METs (Energy Expenditure)")

scatter_plot_path = OUTPUT_DIR / "best_feature_scatter.png"
plt.savefig(scatter_plot_path, dpi=300, bbox_inches='tight')
plt.close()
print(f"Saved: {scatter_plot_path}")

print("\nAll feature visualizations generated successfully! They are ready for your thesis.")
