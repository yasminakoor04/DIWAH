# =============================================================================
# 01_import_raw.R  —  Device data import
# =============================================================================
# Reads raw files for all four devices (ActiGraph, EmotiBit, Bangle, Vyntus),
# runs quality checks, and saves raw_data.rds.
#
# Output: data/processed/raw_data.rds
#   raw_data[[subject_id]]$actigraph        — timestamp, ax, ay, az
#   raw_data[[subject_id]]$emotibit_accel   — timestamp, ax, ay, az
#   raw_data[[subject_id]]$emotibit_ppg     — timestamp, ppg_ir, ppg_red, ppg_green
#   raw_data[[subject_id]]$bangle_accel     — timestamp (rel s), ax, ay, az
#   raw_data[[subject_id]]$bangle_ppg       — timestamp (rel s), ppg
#   raw_data[[subject_id]]$vyntus           — timestamp (elapsed s), hr_polar,
#                                             vo2_absolute, vo2_per_kg, vco2,
#                                             rer, metc, mets, ee_kcal_day,
#                                             ee_kcal_min, ve, bf
# =============================================================================

suppressPackageStartupMessages({
  library(tidyverse)
  library(lubridate)
})
# signal::filter (loaded by 02_feature_extraction.R in the same session) masks
# dplyr::filter. Pin it here so all filter() calls in this script use dplyr.
filter <- dplyr::filter

params    <- readRDS("data/processed/params.rds")
TZ        <- params$tz
BASE_PATH <- params$base_path

# ---- PPG import flag --------------------------------------------------------
# Set FALSE to skip loading PPG signal data (saves time/memory for large datasets).
# Aligned + trimmed timestamps are preserved in data/processed/ppg_time_index.csv
# (written by 02_feature_extraction.R) for use when PPG analysis is resumed.
IMPORT_PPG <- FALSE

PATHS <- list(
  actigraph = "C:/Users/Hanna/Linnéuniversitetet/Oxana Sachenkova - diwah-wearable-anonymized/Actigraph (research device accelerometry)",
  emotibit  = "C:/Users/Hanna/Linnéuniversitetet/Oxana Sachenkova - diwah-wearable-anonymized/emotibit",
  bangle    = "C:/Users/Hanna/Linnéuniversitetet/Oxana Sachenkova - diwah-wearable-anonymized/Bangle",
  vyntus    = "C:/Users/Hanna/Linnéuniversitetet/Oxana Sachenkova - diwah-wearable-anonymized/calorimetry_anonymized"
)

# =============================================================================
# HELPER: Sampling-rate estimate
# =============================================================================
est_hz <- function(ts) {
  if (length(ts) < 2) return(NA_real_)
  ts_num  <- as.numeric(ts)
  dur     <- max(ts_num, na.rm = TRUE) - min(ts_num, na.rm = TRUE)
  if (dur <= 0) return(NA_real_)
  round((length(ts) - 1L) / dur, 1)
}

# =============================================================================
# HELPER: Quality report for one device data frame
# =============================================================================
qc_report <- function(df, device_name, subject_id, key_cols = c("ax", "ay", "az")) {
  if (is.null(df)) {
    message(sprintf("    [%s | %s] NOT FOUND — skipping", subject_id, device_name))
    return(invisible(NULL))
  }
  n_rows  <- nrow(df)
  ts_col  <- df$timestamp
  t_range <- if (inherits(ts_col, "POSIXct")) {
    sprintf("%s  to  %s", format(min(ts_col), "%H:%M:%S"), format(max(ts_col), "%H:%M:%S"))
  } else {
    sprintf("%.1f s  to  %.1f s", min(ts_col, na.rm = TRUE), max(ts_col, na.rm = TRUE))
  }
  hz   <- est_hz(ts_col)
  miss <- sapply(intersect(key_cols, names(df)), function(col) sum(is.na(df[[col]])))

  message(sprintf("    [%s | %s]  rows=%d  range=%s  ~%.1f Hz  NA=%s",
    subject_id, device_name, n_rows, t_range, hz,
    paste(names(miss), miss, sep = ":", collapse = " ")))

  if (n_rows < 100)
    warning(sprintf("WARNING [%s | %s]: fewer than 100 rows (%d)", subject_id, device_name, n_rows))
  if (!is.na(hz)) {
    expected_hz <- list(actigraph = 30, emotibit = 25, bangle = 25)
    for (dev in names(expected_hz)) {
      if (grepl(dev, tolower(device_name)) && abs(hz - expected_hz[[dev]]) > 5)
        warning(sprintf("WARNING [%s | %s]: implausible Hz=%.1f (expected ~%d)",
                        subject_id, device_name, hz, expected_hz[[dev]]))
    }
  }
}

# =============================================================================
# READER: ActiGraph GT3X+
# =============================================================================
# Format: 10 metadata rows, header on row 11, data from row 12.
# Timestamps quoted strings, values quoted with comma as decimal separator.
read_actigraph <- function(file, max_hours = 4, expected_time = NULL) {
  # Detect header row (line starting with "Timestamp")
  preview  <- readLines(file, n = 15, warn = FALSE)
  hdr_row  <- which(grepl("^[\"']?Timestamp", preview))
  skip_n   <- if (length(hdr_row)) hdr_row[1] - 1L else 10L

  norm_names <- function(nms) {
    nms %>%
      str_replace_all("[^A-Za-z0-9]", "_") %>%
      str_replace_all("_+", "_") %>%
      str_to_lower() %>%
      str_replace_all("^_|_$", "")
  }

  parse_raw <- function(raw) {
    names(raw) <- norm_names(names(raw))
    raw %>%
      transmute(
        timestamp = ymd_hms(timestamp, tz = TZ, quiet = TRUE),
        ax        = as.numeric(str_replace_all(accelerometer_x, ",", ".")),
        ay        = as.numeric(str_replace_all(accelerometer_y, ",", ".")),
        az        = as.numeric(str_replace_all(accelerometer_z, ",", "."))
      ) %>%
      filter(!is.na(timestamp))
  }

  fsize <- file.info(file)$size

  # For very large files (>100 MB), read max_hours centred on expected_time.
  # If expected_time is NULL, fall back to reading the last max_hours of data.
  if (fsize > 100e6) {
    max_rows <- as.integer(max_hours * 3600 * 30)  # 30 Hz

    # Read sample lines to estimate bytes/row and get file-start timestamp
    n_sample_lines <- skip_n + 1L + 200L  # metadata + col header + 200 data rows
    sample_lines   <- readLines(file, n = n_sample_lines, warn = FALSE)
    data_lines     <- sample_lines[seq(skip_n + 2L, length(sample_lines))]
    # +2 per line for CRLF (Windows) or +1 for LF (Unix)
    bytes_per_row  <- mean(nchar(data_lines, type = "bytes") + 2L)
    col_nms        <- strsplit(sample_lines[skip_n + 1L], ",")[[1]]
    # Remove quotes from header
    col_nms        <- gsub('^["\']|["\']$', "", col_nms)

    # Estimate header size and total rows
    hdr_bytes      <- sum(nchar(sample_lines[seq_len(skip_n + 1L)], type = "bytes") + 2L)
    data_bytes     <- fsize - hdr_bytes
    est_total_rows <- as.integer(data_bytes / bytes_per_row)

    # --- Decide start byte offset -------------------------------------------
    # Use expected_time to seek directly by byte offset (avoids scanning millions
    # of rows to count newlines, which makes read_csv very slow on large files).
    # Fall back to "last N hours" when expected_time is unavailable.
    seek_byte <- if (!is.null(expected_time)) {
      first_field  <- strsplit(data_lines[1], ",")[[1]][1]
      first_field  <- gsub('^["\']|["\']$', "", first_field)
      t_file_start <- suppressWarnings(ymd_hms(first_field, tz = TZ, quiet = TRUE))

      if (!is.na(t_file_start)) {
        secs_to_target <- as.numeric(difftime(expected_time, t_file_start, units = "secs"))
        # Start 10 min (600 s) before expected_time for safety
        secs_before    <- max(0, secs_to_target - 600)
        target_byte    <- hdr_bytes + secs_before * 30 * bytes_per_row
        message(sprintf(
          "    Large ActiGraph file (%.0f MB, ~%d rows, file start ~%s): byte-seeking to test at %s.",
          fsize / 1e6, est_total_rows,
          format(t_file_start, "%Y-%m-%d %H:%M"),
          format(expected_time, "%Y-%m-%d %H:%M")))
        max(0, target_byte)
      } else {
        message(sprintf(
          "    Large ActiGraph file (%.0f MB): could not parse first timestamp; reading last ~%.0f hours.",
          fsize / 1e6, max_hours))
        hdr_bytes + max(0, est_total_rows - max_rows * 1.1) * bytes_per_row
      }
    } else {
      message(sprintf(
        "    Large ActiGraph file (%.0f MB, ~%d rows): no expected_time given; reading last ~%.0f hours.",
        fsize / 1e6, est_total_rows, max_hours))
      hdr_bytes + max(0, est_total_rows - max_rows * 1.1) * bytes_per_row
    }

    # --- Read via binary seek + readLines (avoids slow row-skip in read_csv) --
    # Binary seek to approximate position, discard the partial first line, then
    # read at most max_rows complete lines and parse as CSV.
    raw <- tryCatch({
      con <- file(file, open = "rb")
      on.exit(try(close(con), silent = TRUE), add = TRUE)
      seek(con, where = as.numeric(seek_byte), origin = "start", rw = "read")
      readLines(con, n = 1L, warn = FALSE)   # discard partial first row
      txt_lines <- readLines(con, n = max_rows, warn = FALSE)
      close(con)
      on.exit(NULL, add = FALSE)   # clear the on.exit since we closed manually
      if (!length(txt_lines)) stop("no lines read after seek")
      tsv_text <- paste(c(paste(col_nms, collapse = ","), txt_lines), collapse = "\n")
      raw_parsed <- read_csv(I(tsv_text),
                             col_types = cols(.default = col_character()),
                             show_col_types = FALSE, progress = FALSE)
      names(raw_parsed) <- norm_names(names(raw_parsed))
      raw_parsed
    }, error = function(e) {
      warning(sprintf("Byte-seek read failed (%s); falling back to full-file read.", e$message))
      read_csv(file, skip = skip_n,
               col_types = cols(.default = col_character()),
               show_col_types = FALSE, progress = FALSE)
    })
  } else {
    raw <- read_csv(file, skip = skip_n,
                    col_types = cols(.default = col_character()),
                    show_col_types = FALSE, progress = FALSE)
  }

  trim_inactive_ag(parse_raw(raw))
}

# =============================================================================
# HELPER: Non-wear detection and removal for ActiGraph
# =============================================================================
# Non-wear = device initialised but not yet attached (lying on a table/charger),
# or left recording after removal.  Characterised by near-constant VM (gravity
# only) → very low epoch SD.
#
# Algorithm
# ---------
# 1. Compute VM SD per epoch_sec window (default 60 s — stable, not tricked by
#    a single table bump).
# 2. Classify each epoch as WEAR if SD >= min_sd, NON-WEAR otherwise.
# 3. Short non-wear runs (< min_nonwear_sec) are re-classified as WEAR so that
#    brief pauses INSIDE the test are never removed.
# 4. Dilate the surviving WEAR mask by margin_sec in both directions.
# 5. Remove everything outside the dilated mask.
# 6. If nothing qualifies as WEAR, return the data unchanged (safety fallback).
#
# Parameters
# ----------
# margin_sec      Buffer kept around any wear epoch (default 5 min).
# epoch_sec       Window for SD computation (default 60 s).
# min_sd          VM SD threshold below which an epoch is non-wear (default
#                 0.013 g — consistent with GGIR / van Hees 2011 raw-data
#                 non-wear criterion).
# min_nonwear_sec Only remove an inactive run if it lasts at least this long
#                 (default 5 min).  Prevents removing brief rest intervals.
trim_inactive_ag <- function(df,
                             margin_sec      = 300,
                             epoch_sec       = 60,
                             min_sd          = 0.013,
                             min_nonwear_sec = 300) {
  if (is.null(df) || nrow(df) == 0) return(df)

  df <- df %>%
    mutate(
      vm     = sqrt(ax^2 + ay^2 + az^2),
      ep_bin = floor(as.numeric(timestamp) / epoch_sec) * epoch_sec
    )

  ep_stats <- df %>%
    group_by(ep_bin) %>%
    summarise(vm_sd = sd(vm, na.rm = TRUE), .groups = "drop") %>%
    arrange(ep_bin) %>%
    mutate(active = !is.na(vm_sd) & vm_sd >= min_sd)

  if (!any(ep_stats$active, na.rm = TRUE)) {
    # No wear detected at all — return as-is (don't silently discard everything)
    message("    Non-wear detection: no active epochs found; keeping all data.")
    return(df %>% select(-vm, -ep_bin))
  }

  # ---- Step 3: re-activate short non-wear runs --------------------------------
  # A non-wear run shorter than min_nonwear_sec is a brief pause, not true
  # non-wear.  Force it back to WEAR so the margin dilation keeps it.
  min_nonwear_ep <- ceiling(min_nonwear_sec / epoch_sec)
  rl   <- rle(ep_stats$active)
  idx  <- 1L
  for (i in seq_along(rl$lengths)) {
    if (!rl$values[i] && rl$lengths[i] < min_nonwear_ep)
      ep_stats$active[idx : (idx + rl$lengths[i] - 1L)] <- TRUE
    idx <- idx + rl$lengths[i]
  }

  # ---- Step 4: dilate the wear mask by margin_sec ----------------------------
  margin_ep <- ceiling(margin_sec / epoch_sec)
  n          <- nrow(ep_stats)
  keep       <- logical(n)
  for (i in which(ep_stats$active)) {
    keep[max(1L, i - margin_ep) : min(n, i + margin_ep)] <- TRUE
  }

  # ---- Step 5: remove non-wear rows ------------------------------------------
  keep_bins <- ep_stats$ep_bin[keep]
  n_before  <- nrow(df)
  df        <- df %>% filter(ep_bin %in% keep_bins)
  n_removed <- n_before - nrow(df)

  if (n_removed > 0) {
    n_wear_min    <- sum(keep)     * epoch_sec / 60
    n_nonwear_min <- n_removed     / 30        / 60
    message(sprintf(
      "    Non-wear removed: %.0f min  |  wear retained: %.0f min  (SD < %.3f g, run >= %.0f min)",
      n_nonwear_min, n_wear_min, min_sd, min_nonwear_sec / 60))
  }

  df %>% select(-vm, -ep_bin)
}

# =============================================================================
# READER: EmotiBit
# =============================================================================
# Each signal is a separate CSV. LocalTimestamp = Unix epoch (float, UTC).
# AX/AY/AZ (and PI/PR/PG) have matching row counts — join by row index.
read_emotibit <- function(folder, include_ppg = TRUE) {
  all_files <- list.files(folder, pattern = "\\.csv$", full.names = TRUE)
  # Exclude ERROR files
  all_files <- all_files[!grepl("_ERROR\\.csv$", all_files, ignore.case = TRUE)]

  read_em_stream <- function(suffix) {
    # 1. Try split files (e.g. _AX.csv)
    f_split <- all_files[grepl(paste0("_", suffix, "\\.csv$"), all_files)]
    if (length(f_split)) {
      raw <- suppressMessages(read_csv(f_split[1], show_col_types = FALSE, progress = FALSE))
      return(data.frame(
        timestamp = as.POSIXct(raw$LocalTimestamp, origin = "1970-01-01", tz = "UTC") %>% with_tz(TZ),
        value = pull(raw, last_col()),
        stringsAsFactors = FALSE
      ))
    }
    
    # 2. Try monolithic file directly off the SD card
    f_mono <- all_files[!grepl("_ERROR\\.csv$", all_files, ignore.case=TRUE) & !grepl("info\\.json$", all_files, ignore.case=TRUE)]
    if (!length(f_mono)) return(NULL)
    
    lines <- readLines(f_mono[1], warn = FALSE)
    t_lines <- lines[grepl(paste0(",", suffix, ","), lines)]
    if (!length(t_lines)) return(NULL)
    
    # Just grab the first timestamp (col 1) and first payload value (col 7) for visual alignment
    splits <- strsplit(t_lines, ",")
    ts_ms <- as.numeric(sapply(splits, `[`, 1))
    vals <- as.numeric(sapply(splits, `[`, 7))
    
    ts_sec <- ts_ms / 1000.0 # monolithic LocalTimestamp is in milliseconds
    
    if (max(ts_sec, na.rm=TRUE) < 1e9) {
      # Device clock was relative/unsynced; return numeric so alignment_app maps it to Actigraph
      data.frame(
        timestamp = ts_sec,
        value = vals,
        stringsAsFactors = FALSE
      )
    } else {
      # True Unix Epoch
      data.frame(
        timestamp = as.POSIXct(ts_sec, origin = "1970-01-01", tz = "UTC") %>% with_tz(TZ),
        value = vals,
        stringsAsFactors = FALSE
      )
    }
  }

  ax <- read_em_stream("AX"); ay <- read_em_stream("AY"); az <- read_em_stream("AZ")

  accel <- if (!is.null(ax) && !is.null(ay) && !is.null(az)) {
    n  <- min(nrow(ax), nrow(ay), nrow(az))
    data.frame(
      timestamp = ax$timestamp[1:n],
      ax        = ax$value[1:n],
      ay        = ay$value[1:n],
      az        = az$value[1:n],
      stringsAsFactors = FALSE
    ) %>% arrange(timestamp)
  } else NULL

  # PPG channels (PI = infrared, PR = red, PG = green) — only read when requested
  ppg <- if (include_ppg) {
    pi <- read_em_stream("PI"); pr <- read_em_stream("PR"); pg <- read_em_stream("PG")
    if (!is.null(pi) && !is.null(pr) && !is.null(pg)) {
      n  <- min(nrow(pi), nrow(pr), nrow(pg))
      data.frame(
        timestamp = pi$timestamp[1:n],
        ppg_ir    = pi$value[1:n],
        ppg_red   = pr$value[1:n],
        ppg_green = pg$value[1:n],
        stringsAsFactors = FALSE
      ) %>% arrange(timestamp)
    } else NULL
  } else NULL

  list(accel = accel, ppg = ppg)
}

# =============================================================================
# READER: Bangle
# =============================================================================
# Time column = inter-sample interval in ms; cumsum gives elapsed ms.
# No absolute timestamp — output timestamp is seconds from start of recording.
read_bangle <- function(file, include_ppg = TRUE) {
  raw <- suppressMessages(
    read_csv(file, show_col_types = FALSE, progress = FALSE)
  ) %>% rename_with(str_to_lower)

  # Build relative timestamp in seconds
  raw <- raw %>%
    mutate(
      elapsed_ms = cumsum(time),
      timestamp  = elapsed_ms / 1000  # seconds from recording start
    )

  accel <- raw %>%
    transmute(timestamp, ax = acc_x, ay = acc_y, az = acc_z)

  # Red PPG channel (PPG_r) is the primary channel — only read when requested
  ppg <- if (include_ppg) {
    ppg_col <- intersect(c("ppg_r", "ppgr", "ppg"), names(raw))
    if (length(ppg_col)) raw %>% transmute(timestamp, ppg = .data[[ppg_col[1]]]) else NULL
  } else NULL

  list(accel = accel, ppg = ppg)
}

# =============================================================================
# READER: Vyntus
# =============================================================================
# Tab-separated, ISO-8859-1. 12 header rows + 1 column row + 1 units row.
# Tid = elapsed MM:SS. No absolute start time in file (flag + warn).
# Last rows may be cool-down (empty VO2) and a footer line.
read_vyntus <- function(file) {
  # Attempt 1: text-based read (handles plain TSV and text-disguised .xls)
  raw_lines <- tryCatch(
    readLines(file, encoding = "latin1", warn = FALSE),
    error = function(e) character(0)
  )

  # If the file is binary Excel (.xls/.xlsx), readLines returns garbage; fall back
  # to readxl (if installed) which converts the sheet to a data frame directly.
  tid_row <- which(grepl("^Tid\t|^\"?Tid\"?\t|^Tid$", raw_lines))
  if (!length(tid_row) && grepl("\\.(xls|xlsx)$", file, ignore.case = TRUE)) {
    if (!requireNamespace("readxl", quietly = TRUE)) {
      warning(sprintf("Vyntus: %s appears to be binary Excel but 'readxl' is not installed.",
                      basename(file)))
      return(NULL)
    }
    df_xl <- tryCatch(
      readxl::read_excel(file, col_types = "text"),
      error = function(e) {
        warning(sprintf("Vyntus: readxl failed for %s: %s", basename(file), e$message))
        NULL
      }
    )
    if (is.null(df_xl)) return(NULL)
    # Convert the readxl data frame to the tab-separated text format expected below
    raw_lines <- c(
      paste(names(df_xl), collapse = "\t"),  # synthetic header
      "",                                     # blank units row (skipped below)
      apply(df_xl, 1, paste, collapse = "\t")
    )
    tid_row <- 1L
  }

  # Find column header row (contains "Tid" as first field)
  col_row <- if (length(tid_row)) tid_row[1] else
    which(grepl("^Tid\t|^\"?Tid\"?\t|^Tid$", raw_lines))[1]
  if (is.na(col_row) || !length(col_row)) {
    warning(sprintf("Vyntus: cannot find column header row in %s", basename(file)))
    return(NULL)
  }
  col_row <- col_row[1]

  # Check header text for absolute start time (not present in current files — warn)
  header_text <- paste(raw_lines[seq_len(col_row - 1)], collapse = "\n")
  start_found <- grepl("[0-9]{2}:[0-9]{2}:[0-9]{2}", header_text) &&
                 grepl("[0-9]{4}-[0-9]{2}-[0-9]{2}", header_text)
  if (!start_found) {
    message(sprintf("    NOTE: No absolute start timestamp found in Vyntus file %s.",
                    basename(file)))
    message("          Timestamp will be stored as elapsed seconds (relative).")
    message("          Absolute alignment will use cross-correlation in the Shiny app.")
  }

  # Data starts after column row + units row
  data_start <- col_row + 2L
  data_lines <- raw_lines[data_start:length(raw_lines)]

  # Remove footer and blank lines
  data_lines <- data_lines[!grepl("^Efternamn:|^Förnamn:|^Kön:|^Vikt:|^Längd:|^Ålder:|^Födelse|^BMI", data_lines)]
  data_lines <- data_lines[nzchar(trimws(data_lines))]

  if (!length(data_lines)) return(NULL)

  # Combine header row with data and parse as TSV
  tsv_text <- paste(c(raw_lines[col_row], data_lines), collapse = "\n")
  df <- suppressMessages(
    read_tsv(I(tsv_text),
             col_types = cols(.default = col_character()),
             locale    = locale(encoding = "latin1"),
             progress  = FALSE)
  )

  # Rename columns (handle prime character in V'O2 etc.)
  rename_map <- c(
    "Tid"       = "tid",
    "HR"        = "hr_polar",
    "V.E"       = "ve",          # V'E
    "BF"        = "bf",
    "V.O2"      = "vo2_absolute",
    "V.CO2"     = "vco2",
    "RER"       = "rer",
    "V.O2.kg"   = "vo2_per_kg",
    "METc"      = "metc",
    "METS"      = "mets",
    "EF.d"      = "ee_kcal_day"
  )
  # Build a flexible rename: strip non-alphanumeric, match
  colkey <- names(df) %>% str_replace_all("[^A-Za-z0-9]", ".")
  names(df) <- str_replace_all(names(df), "[^A-Za-z0-9]", ".")
  for (orig in names(rename_map)) {
    idx <- which(str_detect(names(df), fixed(orig)))
    if (length(idx)) names(df)[idx[1]] <- rename_map[orig]
  }

  # Convert numerics — replace comma decimals (Swedish locale) before coercion
  df <- df %>%
    mutate(across(-tid, ~ suppressWarnings(as.numeric(str_replace_all(.x, ",", ".")))))

  # Parse Tid (MM:SS or " MM:SS" with leading space) to elapsed seconds
  df <- df %>%
    mutate(
      m = suppressWarnings(as.integer(str_extract(tid, "\\d+(?=:)"))),
      s = suppressWarnings(as.integer(str_extract(tid, "(?<=:)\\d+"))),
      timestamp = if_else(!is.na(m) & !is.na(s), m * 60 + s, NA_real_)
    ) %>%
    filter(!is.na(timestamp)) %>%
    mutate(ee_kcal_min = ee_kcal_day / 1440) %>%
    select(timestamp, hr_polar, vo2_absolute, vo2_per_kg, vco2, rer,
           metc, mets, ee_kcal_day, ee_kcal_min, ve, bf) %>%
    arrange(timestamp)

  df
}

# =============================================================================
# DISCOVER ALL SUBJECTS
# =============================================================================
discover_subjects <- function() {
  extract_id <- function(paths, pattern, sub_pattern) {
    f <- list.files(paths, pattern = pattern, full.names = FALSE)
    unique(str_extract(f, sub_pattern)) %>% na.omit() %>% as.character()
  }

  ag_ids <- list.files(PATHS$actigraph, pattern = "\\.csv$") %>%
    str_extract("^[0-9]+") %>% na.omit()
  em_ids <- list.dirs(PATHS$emotibit, recursive = FALSE, full.names = FALSE) %>%
    str_extract("^[0-9]+") %>% na.omit()
  bg_ids <- list.files(PATHS$bangle, pattern = "\\.csv$") %>%
    str_extract("^[0-9]+") %>% na.omit()
  # List all files (no extension filter) — production batch files have no extension
  vn_ids <- list.files(PATHS$vyntus) %>%
    str_extract("^[0-9]+") %>% na.omit()

  sort(unique(c(ag_ids, em_ids, bg_ids, vn_ids)))
}

find_file <- function(dir, id, pattern) {
  f <- list.files(dir, full.names = TRUE)
  f <- f[grepl(paste0("^", id, "[^0-9]"), basename(f)) &
         grepl(pattern, basename(f), ignore.case = TRUE)]
  if (length(f)) f[1] else NULL
}

find_emotibit_folder <- function(id) {
  dirs <- list.dirs(PATHS$emotibit, recursive = FALSE, full.names = TRUE)
  match <- dirs[grepl(paste0("^", id, "[^0-9]"), basename(dirs))]
  if (length(match)) match[1] else NULL
}

# =============================================================================
# MAIN IMPORT LOOP
# =============================================================================
subjects <- discover_subjects()
message(sprintf("\nDiscovered %d subjects: %s", length(subjects), paste(subjects, collapse = ", ")))

# Load existing trim windows to guide large-file ActiGraph reading (if available).
# Force start_time/end_time as character — readr would otherwise parse them as
# UTC datetimes, shifting Stockholm local times by 2 h in summer (CEST = UTC+2).
trim_wins_existing <- tryCatch(
  read_csv("data/processed/trim_windows.csv", show_col_types = FALSE,
           col_types = cols(subject_id = col_character(),
                            start_time = col_character(),
                            end_time   = col_character())),
  error = function(e) NULL
)
if (!is.null(trim_wins_existing))
  message("  Using trim_windows.csv to guide large-file ActiGraph reading.")

raw_data <- list()

for (sid in subjects) {
  message(sprintf("\n--- Subject %s ---", sid))

  # Expected test start time for this subject (used to seek in large AG files)
  expected_ag_time <- if (!is.null(trim_wins_existing) &&
                           sid %in% as.character(trim_wins_existing$subject_id)) {
    row <- trim_wins_existing[as.character(trim_wins_existing$subject_id) == sid, ]
    as.POSIXct(row$start_time[1], tz = TZ)
  } else NULL

  # ActiGraph
  ag_file <- find_file(PATHS$actigraph, sid, "RAW\\.csv$")
  ag_data <- if (!is.null(ag_file)) {
    tryCatch(read_actigraph(ag_file, expected_time = expected_ag_time), error = function(e) {
      warning(sprintf("[%s] ActiGraph import failed: %s", sid, e$message)); NULL
    })
  } else NULL
  qc_report(ag_data, "ActiGraph", sid)

  # EmotiBit
  em_folder <- find_emotibit_folder(sid)
  em_result <- if (!is.null(em_folder)) {
    tryCatch(read_emotibit(em_folder, include_ppg = IMPORT_PPG), error = function(e) {
      warning(sprintf("[%s] EmotiBit import failed: %s", sid, e$message)); list(accel = NULL, ppg = NULL)
    })
  } else list(accel = NULL, ppg = NULL)
  qc_report(em_result$accel, "EmotiBit_accel", sid)
  if (IMPORT_PPG)
    qc_report(em_result$ppg, "EmotiBit_ppg", sid, key_cols = c("ppg_ir", "ppg_red", "ppg_green"))

  # Bangle
  bg_file   <- find_file(PATHS$bangle, sid, "\\.csv$")
  bg_result <- if (!is.null(bg_file)) {
    tryCatch(read_bangle(bg_file, include_ppg = IMPORT_PPG), error = function(e) {
      warning(sprintf("[%s] Bangle import failed: %s", sid, e$message)); list(accel = NULL, ppg = NULL)
    })
  } else list(accel = NULL, ppg = NULL)
  qc_report(bg_result$accel, "Bangle_accel", sid)
  if (IMPORT_PPG)
    qc_report(bg_result$ppg, "Bangle_ppg", sid, key_cols = "ppg")

  # Vyntus
  # Accept any extension (or none) — "." matches every filename character
  vn_file <- find_file(PATHS$vyntus, sid, ".")
  vn_data <- if (!is.null(vn_file)) {
    tryCatch(read_vyntus(vn_file), error = function(e) {
      warning(sprintf("[%s] Vyntus import failed: %s", sid, e$message)); NULL
    })
  } else NULL
  qc_report(vn_data, "Vyntus", sid, key_cols = c("hr_polar", "vo2_absolute"))

  raw_data[[sid]] <- list(
    actigraph      = ag_data,
    emotibit_accel = em_result$accel,
    emotibit_ppg   = em_result$ppg,
    bangle_accel   = bg_result$accel,
    bangle_ppg     = bg_result$ppg,
    vyntus         = vn_data
  )
}

# =============================================================================
# SAVE
# =============================================================================
saveRDS(raw_data, "data/processed/raw_data.rds")
message(sprintf("\nRaw data saved: data/processed/raw_data.rds  (%d subjects)", length(raw_data)))
message("Import complete.")
