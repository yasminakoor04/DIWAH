# =============================================================================
# main.R  —  Pipeline orchestration
# =============================================================================
# Run order:
#   1. source("main.R")          — runs everything flagged TRUE
#   2. Or run source() calls individually below
# =============================================================================

# ---- Set working directory to project root -----------------------------------
BASE_PATH <- "C:/Users/Hanna/Downloads/OneDrive_1_4-2-2026"
if (!dir.exists(BASE_PATH))
  stop("BASE_PATH not found. Update it in main.R to match your machine.")
setwd(BASE_PATH)
message("Working directory: ", getwd())

# ---- Global parameters -------------------------------------------------------
params <- list(
  epoch_sec            = 5,
  stage_sec            = 120,
  epochs_per_stage     = 24,
  steady_state_start   = 19,        # epoch within stage where SS begins
  auto_align_threshold = 0.7,       # min xcor to accept auto-alignment
  tertile_low_mod      = 40,        # %VO2peak boundary low/moderate
  tertile_mod_high     = 70,        # %VO2peak boundary moderate/high
  hr_error_threshold   = 10,        # bpm
  ee_error_threshold   = 10,        # %
  tz                   = "Europe/Stockholm",
  col_actigraph        = "#2166AC",
  col_emotibit         = "#1B7837",
  col_bangle           = "#D6604D",
  col_polar            = "#8B0000",
  col_vo2              = "#FF8C00",
  base_path = "C:/Users/Hanna/Downloads/OneDrive_1_4-2-2026"
)
dir.create("data/processed", recursive = TRUE, showWarnings = FALSE)
dir.create("data/results",   recursive = TRUE, showWarnings = FALSE)
dir.create("output/figures", recursive = TRUE, showWarnings = FALSE)
dir.create("output/tables",  recursive = TRUE, showWarnings = FALSE)

saveRDS(params, "data/processed/params.rds")
message("Parameters saved to data/processed/params.rds")

# ---- Step flags --------------------------------------------------------------
run_step <- c(
  import_raw      = TRUE,
  alignment_app   = TRUE,
  feature_extract = TRUE
)

# ---- Step 1: import raw data -------------------------------------------------
if (run_step["import_raw"]) {
  message("\n========== STEP 1: Import raw data ==========")
  source("01_import_raw.R")
}

# ---- Step 2: alignment & trimming Shiny app ----------------------------------
if (run_step["alignment_app"]) {
  message("\n========== STEP 2: Alignment & trimming app ==========")
  message("App will open in browser. Close it when all subjects are confirmed.")
  source("alignment_app.R")
  # Pipeline pauses here until the app window is closed.
  
  confirmed <- tryCatch(
    read.csv("data/processed/trim_windows.csv", stringsAsFactors = FALSE),
    error = function(e) data.frame(confirmed = logical(0))
  )
  n_confirmed <- sum(confirmed$confirmed == TRUE, na.rm = TRUE)
  n_total     <- nrow(confirmed)
  message(sprintf("%d of %d subjects confirmed in alignment app.", n_confirmed, n_total))
  if (n_confirmed < n_total) {
    stop(paste0("Not all subjects confirmed. ",
                "Re-run the alignment app (run_step['alignment_app'] = TRUE) before proceeding."))
  }
}

# ---- Step 3: feature extraction ----------------------------------------------
if (run_step["feature_extract"]) {
  message("\n========== STEP 3: Feature extraction ==========")
  source("02_feature_extraction.R")
}

message("\n========== Pipeline stage 1 complete ==========")
message("master_epochs.csv is ready for analysis.")
message("Next: run scripts 03 onwards for PPG-HR, statistics, and ML models.")
