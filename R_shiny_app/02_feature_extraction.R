# =============================================================================
# 02_feature_extraction.R  —  5-second epoch feature extraction
# =============================================================================
# Input:
#   data/processed/raw_data.rds
#   data/processed/trim_windows.csv   (must be fully confirmed)
#   data/processed/alignment_offsets.csv
#
# Output:
#   data/processed/master_epochs.rds / .csv
#   data/processed/steady_state_epochs.csv
# =============================================================================

suppressPackageStartupMessages({
  library(signal)
  library(tidyverse)
  library(lubridate)
})
# signal::filter masks dplyr::filter regardless of load order in some sessions.
# Pin filter explicitly so %>% filter(...) always calls dplyr.
filter <- dplyr::filter

params    <- readRDS("data/processed/params.rds")
TZ        <- params$tz
EPOCH_SEC <- params$epoch_sec
STAGE_SEC <- params$stage_sec
SS_START  <- params$steady_state_start   # epoch_within_stage >= this -> steady state

raw_data  <- readRDS("data/processed/raw_data.rds")
# Force start_time/end_time as character so readr does NOT auto-parse them as
# UTC datetimes (readr would shift Stockholm local times by 2 h in summer).
# as.POSIXct(..., tz=TZ) below then correctly interprets the local-time string.
trim_wins <- read_csv("data/processed/trim_windows.csv",  show_col_types = FALSE,
                      col_types = cols(subject_id  = col_character(),
                                       start_time  = col_character(),
                                       end_time    = col_character()))
offsets   <- read_csv("data/processed/alignment_offsets.csv", show_col_types = FALSE,
                      col_types = cols(subject_id = col_character()))
# AG options: per-subject exclusion and crop decisions saved by the alignment app.
# NULL when file not yet created (no AG options set).
ag_opts   <- tryCatch(
  read_csv("data/processed/ag_options.csv", show_col_types = FALSE,
           col_types = cols(subject_id    = col_character(),
                            ag_excluded   = col_logical(),
                            ag_crop_start = col_character(),
                            ag_crop_end   = col_character())),
  error = function(e) NULL
)

# =============================================================================
# PRE-FLIGHT CHECK
# =============================================================================
n_total <- nrow(trim_wins)
n_conf  <- sum(trim_wins$confirmed == TRUE, na.rm = TRUE)
message(sprintf("Pre-flight: %d / %d subjects confirmed.", n_conf, n_total))
unconf_sids <- trim_wins %>% filter(!confirmed) %>% pull(subject_id)
if (length(unconf_sids))
  warning(sprintf("Skipping unconfirmed subjects: %s", paste(unconf_sids, collapse = ", ")))

subjects_to_run <- trim_wins %>%
  filter(confirmed == TRUE) %>%
  pull(subject_id) %>%
  as.character()
message(sprintf("Processing %d subjects: %s\n", length(subjects_to_run),
                paste(subjects_to_run, collapse = ", ")))

# =============================================================================
# HELPER: PPG bandpass filter (0.5–4 Hz)
# =============================================================================
make_bpf <- function(hz, lo = 0.5, hi = 4.0, order = 4) {
  nyq  <- hz / 2
  W    <- c(lo / nyq, hi / nyq)
  W    <- pmax(0.001, pmin(0.999, W))
  tryCatch(butter(order, W, type = "pass"), error = function(e) NULL)
}

apply_bpf <- function(x, filt) {
  if (is.null(filt) || sum(!is.na(x)) < 20) return(x)
  x_clean <- x; x_clean[is.na(x)] <- 0
  tryCatch(as.numeric(signal::filtfilt(filt, x_clean)), error = function(e) x)
}

est_hz_from <- function(ts) {
  ts_num <- as.numeric(ts)
  dur    <- max(ts_num, na.rm = TRUE) - min(ts_num, na.rm = TRUE)
  if (dur <= 0 || length(ts) < 2) return(25)
  round((length(ts) - 1L) / dur)
}

# =============================================================================
# HELPER: Epoch a raw data frame
# =============================================================================
# ts     : POSIXct or numeric (seconds from origin)
# t_start: POSIXct anchor for epoch 1 (trim start)
# Returns data frame with epoch_idx (1-based, seconds from t_start / EPOCH_SEC)
assign_epochs <- function(ts, t_start) {
  if (inherits(ts, "POSIXct")) {
    elapsed <- as.numeric(difftime(ts, t_start, units = "secs"))
  } else {
    # numeric relative seconds — offset already applied, t_start is offset_sec
    elapsed <- ts - as.numeric(t_start)
  }
  pmax(1L, floor(elapsed / EPOCH_SEC) + 1L)
}

# =============================================================================
# HELPER: Epoch aggregation for one accelerometer stream
# =============================================================================
epoch_accel <- function(df_raw, t_start, t_end, label) {
  # df_raw has columns: timestamp, ax, ay, az  (timestamp is POSIXct)
  if (is.null(df_raw) || nrow(df_raw) == 0) return(NULL)

  df_raw %>%
    filter(timestamp >= t_start, timestamp <= t_end) %>%
    mutate(
      vm        = sqrt(ax^2 + ay^2 + az^2),
      epoch_idx = assign_epochs(timestamp, t_start)
    ) %>%
    group_by(epoch_idx) %>%
    summarise(
      vm_mean = mean(vm,  na.rm = TRUE),
      vm_sd   = sd(vm,    na.rm = TRUE),
      vm_max  = max(vm,   na.rm = TRUE),
      ax_mean = mean(ax,  na.rm = TRUE),
      ay_mean = mean(ay,  na.rm = TRUE),
      az_mean = mean(az,  na.rm = TRUE),
      n_obs   = n(),
      .groups = "drop"
    ) %>%
    rename_with(~ paste0(., "_", label), -epoch_idx)
}

# =============================================================================
# HELPER: Epoch aggregation for PPG (with bandpass filter)
# =============================================================================
epoch_ppg <- function(df_raw, t_start, t_end, label, value_cols) {
  if (is.null(df_raw) || nrow(df_raw) == 0) return(NULL)

  df <- df_raw %>%
    filter(timestamp >= t_start, timestamp <= t_end) %>%
    mutate(epoch_idx = assign_epochs(timestamp, t_start))

  hz   <- est_hz_from(df_raw$timestamp)
  filt <- make_bpf(hz)

  # Filter each PPG channel
  for (col in value_cols) {
    if (col %in% names(df))
      df[[paste0(col, "_filt")]] <- apply_bpf(df[[col]], filt)
  }

  filt_cols <- paste0(value_cols, "_filt")
  filt_cols <- intersect(filt_cols, names(df))

  df %>%
    group_by(epoch_idx) %>%
    summarise(
      across(all_of(filt_cols),
             list(mean = ~ mean(.x, na.rm = TRUE),
                  sd   = ~ sd(.x,   na.rm = TRUE)),
             .names = "{.col}_{.fn}"),
      .groups = "drop"
    ) %>%
    rename_with(~ str_replace(., "_filt_", "_"), starts_with(filt_cols)) %>%
    rename_with(~ paste0(., "_", label), -epoch_idx)
}

# =============================================================================
# HELPER: Epoch aggregation for Vyntus (relative seconds)
# =============================================================================
epoch_vyntus <- function(df_raw, vn_t_start, t_end_elapsed) {
  # df_raw$timestamp = elapsed seconds from Vyntus start
  # vn_t_start = elapsed seconds that corresponds to trim_start (aligned)
  if (is.null(df_raw) || nrow(df_raw) == 0) return(NULL)

  df <- df_raw %>%
    mutate(elapsed_aligned = timestamp - vn_t_start) %>%
    filter(elapsed_aligned >= 0, elapsed_aligned <= t_end_elapsed) %>%
    mutate(epoch_idx = pmax(1L, floor(elapsed_aligned / EPOCH_SEC) + 1L))

  df %>%
    group_by(epoch_idx) %>%
    summarise(
      hr_polar     = mean(hr_polar,     na.rm = TRUE),
      vo2_absolute = mean(vo2_absolute, na.rm = TRUE),
      vo2_per_kg   = mean(vo2_per_kg,   na.rm = TRUE),
      vco2         = mean(vco2,         na.rm = TRUE),
      rer          = mean(rer,          na.rm = TRUE),
      metc         = mean(metc,         na.rm = TRUE),
      mets         = mean(mets,         na.rm = TRUE),
      ee_kcal_day  = mean(ee_kcal_day,  na.rm = TRUE),
      ee_kcal_min  = mean(ee_kcal_min,  na.rm = TRUE),
      ve           = mean(ve,           na.rm = TRUE),
      bf           = mean(bf,           na.rm = TRUE),
      .groups      = "drop"
    ) %>%
    filter(rowSums(!is.na(select(., -epoch_idx))) > 0)
}

# =============================================================================
# MAIN PROCESSING LOOP
# =============================================================================
all_epochs <- list()

for (sid in subjects_to_run) {
  message(sprintf("Processing subject %s ...", sid))

  d     <- raw_data[[sid]]
  tw    <- trim_wins  %>% filter(subject_id == sid)
  off   <- offsets    %>% filter(subject_id == sid)

  t_start <- as.POSIXct(tw$start_time, tz = TZ)
  t_end   <- as.POSIXct(tw$end_time,   tz = TZ)
  trim_dur_sec <- as.numeric(difftime(t_end, t_start, units = "secs"))

  align_meth <- tw$alignment_method

  # ---- STEP 1 & 2: Shift timestamps and trim --------------------------------
  # All devices use elapsed time from their own start, placed into the
  # ActiGraph reference timeline (same logic as alignment_app.R).
  # Artificial absolute time = ag_abs_start + (device_elapsed) + offset_sec
  # This matches the x-axis shown in the Shiny app and the saved trim times.

  # Apply AG options (exclusion flag saved by alignment app)
  ag_opt <- if (!is.null(ag_opts) && sid %in% ag_opts$subject_id)
    ag_opts[ag_opts$subject_id == sid, ] else NULL
  if (!is.null(ag_opt) && isTRUE(ag_opt$ag_excluded[1])) {
    d$actigraph <- NULL
    message(sprintf("  [%s]  ActiGraph excluded per ag_options.csv", sid))
  }

  ag_abs_start     <- if (!is.null(d$actigraph)) min(d$actigraph$timestamp) else t_start
  ag_abs_start_num <- as.numeric(ag_abs_start)

  # ActiGraph (reference device — elapsed from ag_abs_start, offset = 0)
  ag_raw <- if (!is.null(d$actigraph)) {
    d$actigraph %>%
      mutate(timestamp = as.POSIXct(
               ag_abs_start_num + (as.numeric(timestamp) - ag_abs_start_num) + off$offset_actigraph_sec,
               origin = "1970-01-01", tz = TZ)) %>%
      filter(timestamp >= t_start, timestamp <= t_end)
  } else NULL

  # EmotiBit accel: convert to elapsed from EmotiBit's own start, place in ag timeline
  em_abs_start_num <- if (!is.null(d$emotibit_accel))
    min(as.numeric(d$emotibit_accel$timestamp)) else ag_abs_start_num
  em_raw_ac <- if (!is.null(d$emotibit_accel)) {
    d$emotibit_accel %>%
      mutate(timestamp = as.POSIXct(
               ag_abs_start_num + (as.numeric(timestamp) - em_abs_start_num) + off$offset_emotibit_sec,
               origin = "1970-01-01", tz = TZ)) %>%
      filter(timestamp >= t_start, timestamp <= t_end)
  } else NULL

  # Bangle accel (relative seconds from Bangle start — already elapsed-based)
  bg_raw_ac <- if (!is.null(d$bangle_accel)) {
    d$bangle_accel %>%
      mutate(timestamp = as.POSIXct(ag_abs_start_num + timestamp + off$offset_bangle_sec,
                                    origin = "1970-01-01", tz = TZ)) %>%
      dplyr::filter(timestamp >= t_start, timestamp <= t_end)
  } else NULL

  # PPG streams: not processed at this stage.
  # Aligned + trimmed time windows are saved to data/processed/ppg_time_index.csv
  # (written after the main loop) for use when PPG analysis is resumed.
  em_raw_pp <- NULL
  bg_raw_pp <- NULL

  # ---- STEP 3: Assign stages and epoch_within_stage ------------------------
  n_epochs <- ceiling(trim_dur_sec / EPOCH_SEC)
  epoch_meta <- tibble(
    epoch_num          = seq_len(n_epochs),
    epoch_idx          = epoch_num,           # internal join key (dropped later)
    timestamp          = t_start + (epoch_num - 1) * EPOCH_SEC,
    elapsed_sec        = (epoch_num - 1) * EPOCH_SEC,
    stage              = floor(elapsed_sec / STAGE_SEC) + 1L,
    epoch_within_stage = floor((elapsed_sec %% STAGE_SEC) / EPOCH_SEC) + 1L,
    is_steady_state    = epoch_within_stage >= SS_START
  )

  # ---- STEP 4: Epoch feature computation ------------------------------------
  ag_ep <- epoch_accel(ag_raw,    t_start, t_end, "actigraph")
  em_ep <- epoch_accel(em_raw_ac, t_start, t_end, "emotibit")
  bg_ep <- epoch_accel(bg_raw_ac, t_start, t_end, "bangle")

  # Vyntus: compute elapsed equivalent of trim_start in Vyntus relative time
  vn_ep <- NULL
  if (!is.null(d$vyntus)) {
    # Vyntus offset_vyntus_sec: how many seconds to shift Vyntus relative to AG
    # align_elapsed = 0 corresponds to t_start in absolute time
    # Vyntus t=0 corresponds to ag_abs_start + offset_vyntus_sec (= Vyntus recording start)
    vn_t_start_elapsed <-
      as.numeric(difftime(t_start, ag_abs_start, units = "secs")) - off$offset_vyntus_sec
    t_end_elapsed <- as.numeric(difftime(t_end, t_start, units = "secs"))
    vn_ep <- epoch_vyntus(d$vyntus, vn_t_start_elapsed, t_end_elapsed)
  }

  # ---- Join all epoch features on epoch_idx --------------------------------
  # Skip any NULL tables (device absent or no data in trim window)
  merged <- epoch_meta
  for (ep in list(ag_ep, em_ep, bg_ep, vn_ep)) {
    if (!is.null(ep)) merged <- left_join(merged, ep, by = "epoch_idx")
  }
  merged <- merged %>%
    mutate(subject_id = sid, alignment_method = align_meth) %>%
    select(subject_id, timestamp, epoch_num, stage, epoch_within_stage, is_steady_state,
           alignment_method, everything(), -epoch_idx, -elapsed_sec)

  # ---- STEP 5: Subject-level reference values --------------------------------
  if (!is.null(vn_ep) && "vo2_per_kg" %in% names(merged)) {
    # Peak VO2 = mean of last complete stage
    last_stage_data <- merged %>%
      filter(!is.na(vo2_per_kg)) %>%
      group_by(stage) %>%
      filter(n() == params$epochs_per_stage) %>%
      ungroup() %>%
      filter(stage == max(stage))
    peak_vo2 <- if (nrow(last_stage_data)) mean(last_stage_data$vo2_per_kg, na.rm = TRUE) else
      max(merged$vo2_per_kg, na.rm = TRUE)
    peak_hr  <- max(merged$hr_polar, na.rm = TRUE)

    merged <- merged %>%
      mutate(
        peak_vo2           = peak_vo2,
        peak_hr            = peak_hr,
        vo2_relative_pct   = (vo2_per_kg   / peak_vo2) * 100,
        hr_relative_pct    = (hr_polar      / peak_hr)  * 100,
        intensity_tertile  = case_when(
          vo2_relative_pct <  params$tertile_low_mod  ~ "low",
          vo2_relative_pct <  params$tertile_mod_high ~ "moderate",
          !is.na(vo2_relative_pct)                    ~ "high",
          TRUE ~ NA_character_
        )
      )
  } else {
    merged <- merged %>%
      mutate(peak_vo2 = NA_real_, peak_hr = NA_real_,
             vo2_relative_pct = NA_real_, hr_relative_pct = NA_real_,
             intensity_tertile = NA_character_)
  }

  message(sprintf("  [%s]  %d epochs  |  stages 1-%d  |  %d steady-state",
    sid, nrow(merged), max(merged$stage), sum(merged$is_steady_state)))

  all_epochs[[sid]] <- merged
}

# =============================================================================
# PPG TIME INDEX  (for future PPG analysis — no PPG values, just windows)
# =============================================================================
# Saves the aligned trim windows and device offsets so PPG processing can be
# resumed later without re-running the full pipeline.
ppg_time_index <- trim_wins %>%
  filter(confirmed == TRUE) %>%
  select(subject_id, start_time, end_time) %>%
  left_join(
    offsets %>% select(subject_id, offset_emotibit_sec, offset_bangle_sec),
    by = "subject_id"
  )
write_csv(ppg_time_index, "data/processed/ppg_time_index.csv")
message("PPG time index saved: data/processed/ppg_time_index.csv")

# =============================================================================
# COMPILE MASTER TABLE
# =============================================================================
master_epochs <- bind_rows(all_epochs)

# Standardise column order
key_cols <- c("subject_id", "timestamp", "epoch_num", "stage", "epoch_within_stage",
              "is_steady_state", "intensity_tertile",
              "vo2_relative_pct", "hr_relative_pct", "peak_vo2", "peak_hr",
              "vm_mean_actigraph", "vm_sd_actigraph", "vm_max_actigraph",
              "vm_mean_emotibit",  "vm_sd_emotibit",  "vm_max_emotibit",
              "vm_mean_bangle",    "vm_sd_bangle",    "vm_max_bangle",
              "hr_polar", "vo2_absolute", "vo2_per_kg",
              "ee_kcal_min", "metc", "mets", "rer",
              "alignment_method")

present_key <- intersect(key_cols, names(master_epochs))
other_cols  <- setdiff(names(master_epochs), key_cols)
master_epochs <- master_epochs %>% select(all_of(present_key), all_of(other_cols))

# =============================================================================
# SAVE
# =============================================================================
write_csv(master_epochs, "data/processed/master_epochs.csv")
saveRDS(master_epochs,   "data/processed/master_epochs.rds")

steady_state <- master_epochs %>% filter(is_steady_state == TRUE)
write_csv(steady_state, "data/processed/steady_state_epochs.csv")

# =============================================================================
# QUALITY REPORT
# =============================================================================
message("\n========== Quality Report ==========")
message(sprintf("Total epochs:       %d", nrow(master_epochs)))
message(sprintf("Subjects processed: %d", length(all_epochs)))

per_sub <- master_epochs %>%
  count(subject_id) %>%
  summarise(mean = mean(n), sd = sd(n), min = min(n), max = max(n))
message(sprintf("Epochs per subject: mean=%.0f  sd=%.0f  min=%d  max=%d",
                per_sub$mean, per_sub$sd, per_sub$min, per_sub$max))

if ("intensity_tertile" %in% names(master_epochs)) {
  tert <- master_epochs %>%
    filter(!is.na(intensity_tertile)) %>%
    count(intensity_tertile)
  message("Epochs by intensity tertile:")
  print(as.data.frame(tert))
}

# Device coverage
dev_map <- list(
  ActiGraph = "vm_mean_actigraph",
  EmotiBit  = "vm_mean_emotibit",
  Bangle    = "vm_mean_bangle",
  Vyntus    = "vo2_absolute"
)
message("\nSubjects with complete data per device:")
for (dev in names(dev_map)) {
  col <- dev_map[[dev]]
  if (col %in% names(master_epochs)) {
    n_subs <- master_epochs %>%
      group_by(subject_id) %>%
      summarise(has_dev = any(!is.na(.data[[col]])), .groups = "drop") %>%
      filter(has_dev) %>% nrow()
    message(sprintf("  %-12s : %d / %d subjects", dev, n_subs, length(subjects_to_run)))
  }
}

# Achieved epoch rate
n_ep_expected <- ceiling(as.numeric(difftime(
  as.POSIXct(trim_wins$end_time[trim_wins$confirmed], tz = TZ),
  as.POSIXct(trim_wins$start_time[trim_wins$confirmed], tz = TZ),
  units = "secs")) / EPOCH_SEC)
n_ep_actual   <- master_epochs %>% count(subject_id) %>% pull(n)
message(sprintf("\nExpected vs actual epochs: expected=%.0f  actual=%.0f  (%.1f%%)",
                mean(n_ep_expected), mean(n_ep_actual),
                mean(n_ep_actual) / mean(n_ep_expected) * 100))

message("\nFeature extraction complete.")
message("Outputs: data/processed/master_epochs.rds / .csv")
message("         data/processed/steady_state_epochs.csv")
