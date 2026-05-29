# =============================================================================
# alignment_app.R  —  Shiny alignment and trimming app
# =============================================================================
# Launch options:
#   1.  shiny::runApp("scripts/alignment_app.R")
#   2.  source("scripts/alignment_app.R")  from main.R
#   3.  Click "Run App" in RStudio
# =============================================================================

suppressPackageStartupMessages({
  library(tidyverse)
  library(lubridate)
  library(shiny)
  library(plotly)
})
# signal::filter (loaded earlier in the session by 02_feature_extraction.R) masks
# dplyr::filter inside Shiny reactive closures. Pin it explicitly here.
filter <- dplyr::filter

params    <- readRDS("data/processed/params.rds")
TZ        <- params$tz
EPOCH_SEC <- params$epoch_sec
XCOR_THR  <- params$auto_align_threshold
COL       <- list(ag = params$col_actigraph, em = params$col_emotibit,
                  bg = params$col_bangle,    hr = params$col_polar,
                  vo2 = params$col_vo2,
                  trim_fill = "rgba(173,216,230,0.3)")

raw_data  <- readRDS("data/processed/raw_data.rds")
subjects  <- as.character(names(raw_data))   # ensure character keys

# Safe CSV reader: always returns NULL if missing, always coerces subject_id to character
read_csv_safe <- function(path) {
  if (!file.exists(path)) return(NULL)
  df <- read.csv(path, stringsAsFactors = FALSE)
  if ("subject_id" %in% names(df))
    df$subject_id <- as.character(df$subject_id)
  df
}

# Safe correlation: returns NA instead of warning/error on constant or short vectors
safe_cor <- function(x, y) {
  if (length(x) < 3 || length(y) < 3)        return(NA_real_)
  if (sd(x, na.rm = TRUE) == 0)               return(NA_real_)
  if (sd(y, na.rm = TRUE) == 0)               return(NA_real_)
  tryCatch(cor(x, y, use = "complete.obs"), error = function(e) NA_real_)
}

# =============================================================================
# PRE-ALIGNMENT: Compute 5-second epoch VM and cross-correlate
# =============================================================================

# Epoch using each device's own elapsed time (ignores wall-clock entirely).
# ts can be POSIXct (absolute) or numeric (relative seconds) — both handled
# by converting to numeric and subtracting the device's own minimum.
# Returns a tibble with bin_rel (elapsed seconds from device start) and vm.
epoch_device <- function(ts, vals, epoch_sec = EPOCH_SEC) {
  if (is.null(ts) || !length(ts)) return(NULL)
  t_num   <- as.numeric(ts)
  elapsed <- t_num - min(t_num, na.rm = TRUE)   # 0-based from device start
  bin     <- floor(elapsed / epoch_sec) * epoch_sec
  tibble(bin, vm = sqrt(rowSums(vals^2, na.rm = TRUE))) %>%
    group_by(bin) %>% summarise(vm = mean(vm, na.rm = TRUE), .groups = "drop")
}

# Sliding cross-correlation around a known coarse center.
#
# center_ep   : best prior estimate of lag (in epochs).  For devices with
#               absolute timestamps this comes from the wall-clock difference
#               min(dev_ts) - min(ref_ts); for relative-timestamp devices it
#               is inherited from an already-aligned sibling device.
# max_search_ep: fine-tuning window (±epochs) around center_ep.
#
# The two-stage design (coarse from wall-clock, fine from xcor) is necessary
# because a pure blind xcor with a wide window will find spurious matches when
# one device has a long pre-test recording (e.g. 24 h ActiGraph vs 30 min
# EmotiBit).  By anchoring at the wall-clock estimate first, the search is
# confined to a ±10-minute neighbourhood of the true offset regardless of
# how large the overall time gap is.
xcor_lag <- function(ref_vm, dev_vm, center_ep = 0L, max_search_ep = 120L) {
  center_ep    <- as.integer(round(center_ep))
  max_search_ep <- as.integer(max_search_ep)
  n_ref <- length(ref_vm); n_dev <- length(dev_vm)
  # Require at least 5 min of overlap (60 epochs at 5 s) or 30 % of the
  # shorter signal, whichever is larger.
  min_ov <- max(60L, as.integer(min(n_ref, n_dev) * 0.3))
  best_r <- NA_real_; best_L <- center_ep
  for (L in seq(center_ep - max_search_ep, center_ep + max_search_ep)) {
    rs <- max(1L, 1L + L); re <- min(n_ref, n_dev + L)
    ds <- max(1L, 1L - L); de <- min(n_dev, n_ref - L)
    if (re < rs || de < ds) next
    n_ov <- min(re - rs + 1L, de - ds + 1L)
    if (n_ov < min_ov) next
    r <- tryCatch(
      cor(ref_vm[rs:(rs + n_ov - 1L)], dev_vm[ds:(ds + n_ov - 1L)],
          use = "complete.obs"),
      error = function(e) NA_real_)
    if (!is.na(r) && (is.na(best_r) || r > best_r)) { best_r <- r; best_L <- L }
  }
  list(lag_ep = best_L, lag_sec = best_L * EPOCH_SEC, r = best_r)
}

if (file.exists("data/processed/alignment_offsets.csv")) {
  message("Loading existing manual offsets. Skipping initial auto-computation to prevent data loss.")
  offsets_df <- suppressMessages(read_csv("data/processed/alignment_offsets.csv", show_col_types = FALSE))
} else {
  message("Pre-computing automatic alignment offsets...")
  offsets_list <- list()

  # Fine-tuning window for xcor: ±10 minutes around the coarse estimate.
  # Larger than this is almost certainly a spurious match.
  FINE_EP <- 120L

  for (sid in subjects) {
  d <- raw_data[[sid]]
  ag <- d$actigraph; em <- d$emotibit_accel; bg <- d$bangle_accel; vn <- d$vyntus

  # Epoch all devices using their own elapsed time
  ag_ep <- if (!is.null(ag)) epoch_device(ag$timestamp, ag[c("ax","ay","az")]) else NULL
  em_ep <- if (!is.null(em)) epoch_device(em$timestamp, em[c("ax","ay","az")]) else NULL
  bg_ep <- if (!is.null(bg)) epoch_device(bg$timestamp, bg[c("ax","ay","az")]) else NULL

  # -----------------------------------------------------------------------
  # COARSE OFFSET from wall-clock timestamps (AG and EM have absolute time)
  # This is simply min(em_ts) - min(ag_ts) in seconds, converted to epochs.
  # It is accurate regardless of the magnitude of the gap (5 min or 24 h),
  # so it fixes the case where a blind xcor ±300 ep cannot reach the correct
  # position inside a long multi-day ActiGraph recording.
  # BG has only relative timestamps, so it inherits the EM coarse estimate
  # (both devices are started the same day, close in time).
  # -----------------------------------------------------------------------
  coarse_ag_em_ep <- 0L
  if (!is.null(ag) && !is.null(em)) {
    if (inherits(em$timestamp, "POSIXct")) {
      coarse_sec      <- as.numeric(min(em$timestamp)) - as.numeric(min(ag$timestamp))
      coarse_ag_em_ep <- as.integer(round(coarse_sec / EPOCH_SEC))
      message(sprintf("  [%s]  Wall-clock coarse AG-EM gap: %+.0f s (%+d ep)",
                      sid, coarse_sec, coarse_ag_em_ep))
    } else {
      message(sprintf("  [%s]  EmotiBit has relative timestamps; defaulting coarse gap to 0s", sid))
    }
  }
  coarse_ag_bg_ep <- coarse_ag_em_ep   # best prior for Bangle
  
  # For devices with completely blind relative offsets, search a wider 30-min window
  dynamic_search_ep <- if (coarse_ag_em_ep == 0L) FINE_EP * 3L else FINE_EP

  # -----------------------------------------------------------------------
  # FINE ALIGNMENT: xcor within ±dynamic_search_ep epochs of the coarse center
  # -----------------------------------------------------------------------

  # AG vs EM
  r_ag_em <- NA_real_; off_em <- as.numeric(coarse_ag_em_ep) * EPOCH_SEC
  if (!is.null(ag_ep) && !is.null(em_ep)) {
    res     <- xcor_lag(ag_ep$vm, em_ep$vm,
                        center_ep = coarse_ag_em_ep, max_search_ep = dynamic_search_ep)
    r_ag_em <- res$r
    off_em  <- res$lag_sec
  }

  # AG vs BG  (or EM vs BG when AG absent)
  r_ag_bg <- NA_real_; off_bg <- as.numeric(coarse_ag_bg_ep) * EPOCH_SEC
  if (!is.null(ag_ep) && !is.null(bg_ep)) {
    # BG start is less certain than EM start, so allow more padding
    res     <- xcor_lag(ag_ep$vm, bg_ep$vm,
                        center_ep = coarse_ag_bg_ep, max_search_ep = dynamic_search_ep * 2L)
    r_ag_bg <- res$r
    off_bg  <- res$lag_sec
  } else if (is.null(ag_ep) && !is.null(em_ep) && !is.null(bg_ep)) {
    res     <- xcor_lag(em_ep$vm, bg_ep$vm,
                        center_ep = 0L, max_search_ep = dynamic_search_ep * 2L)
    r_ag_bg <- res$r
    off_bg  <- res$lag_sec
    message(sprintf("  [%s]  No ActiGraph — using EmotiBit as BG reference", sid))
  }

  # Vyntus HR vs AG VM
  # VN timestamp is elapsed from test start (0-based). The test lies at
  # approximately the EM position inside the AG timeline, so center there.
  off_vn <- 0
  if (!is.null(ag_ep) && !is.null(vn)) {
    vn_ep <- tibble(
      bin = floor(vn$timestamp / EPOCH_SEC) * EPOCH_SEC,
      vm  = vn$hr_polar
    ) %>% group_by(bin) %>% summarise(vm = mean(vm, na.rm = TRUE), .groups = "drop") %>%
      filter(!is.na(vm))
    if (nrow(vn_ep) > 5) {
      res    <- xcor_lag(ag_ep$vm, vn_ep$vm,
                         center_ep = coarse_ag_em_ep, max_search_ep = FINE_EP)
      off_vn <- res$lag_sec
    }
  }

  # Flag for review
  has_em <- !is.null(em_ep); has_bg <- !is.null(bg_ep)
  needs_review <- is.null(ag_ep) ||
                  (has_em && (is.na(r_ag_em) || r_ag_em < XCOR_THR)) ||
                  (has_bg && (is.na(r_ag_bg) || r_ag_bg < XCOR_THR))

  offsets_list[[sid]] <- tibble(
    subject_id             = sid,
    offset_actigraph_sec   = 0,
    offset_emotibit_sec    = off_em,
    offset_bangle_sec      = off_bg,
    offset_vyntus_sec      = off_vn,
    alignment_method       = "auto",
    auto_correlation_ag_em = round(r_ag_em, 4),
    auto_correlation_ag_ba = round(r_ag_bg, 4),
    needs_review           = needs_review,
    manual_adjusted        = FALSE
  )
  message(sprintf("  [%s]  r(AG-EM)=%.3f  r(AG-BG)=%.3f  off_em=%+.0fs  off_bg=%+.0fs%s",
    sid, coalesce(r_ag_em, NA_real_), coalesce(r_ag_bg, NA_real_),
    off_em, off_bg, if (needs_review) "  ** NEEDS REVIEW **" else ""))
  }
  offsets_df <- bind_rows(offsets_list)
  write_csv(offsets_df, "data/processed/alignment_offsets.csv")
  message("Alignment offsets saved to data/processed/alignment_offsets.csv")
}

# =============================================================================
# HELPER: Build aligned epoch data for one subject
# =============================================================================
# All devices use their own elapsed time (device start = t=0), then the
# offset shifts each device into the reference timeline.
# Reference anchor: absolute POSIXct of the reference device's first sample
# (ActiGraph if available, else EmotiBit).
# Offset meaning: "device recording started off_sec seconds after reference".
get_aligned_epochs <- function(sid, offsets, ag_excluded = FALSE, ag_crop = NULL) {
  d   <- raw_data[[sid]]
  off <- offsets %>% filter(subject_id == sid)

  # Apply AG options before anything else
  ag_src <- d$actigraph
  if (isTRUE(ag_excluded)) {
    ag_src <- NULL
  } else if (!is.null(ag_crop) && !is.null(ag_crop$t_start)) {
    if (!is.null(ag_src) && nrow(ag_src) > 0) {
      ag_src <- ag_src %>%
        filter(as.numeric(timestamp) >= ag_crop$t_start,
               as.numeric(timestamp) <= ag_crop$t_end)
      if (nrow(ag_src) == 0) ag_src <- NULL
    }
  }

  # Reference absolute start (POSIXct → numeric seconds)
  # Aggressive search for ANY device that still has an absolute time
  ref_dev <- if (!is.null(ag_src) && nrow(ag_src) > 0 && inherits(ag_src$timestamp, "POSIXct")) ag_src else
             if (!is.null(d$vyntus) && nrow(d$vyntus) > 0 && inherits(d$vyntus$timestamp, "POSIXct")) d$vyntus else
             if (!is.null(d$emotibit_accel) && nrow(d$emotibit_accel) > 0 && inherits(d$emotibit_accel$timestamp, "POSIXct")) d$emotibit_accel else NULL
             
  ref_start <- if (!is.null(ref_dev)) min(as.numeric(ref_dev$timestamp), na.rm = TRUE) else 0
  if (!is.finite(ref_start)) ref_start <- 0
  
  # Failsafe: if ALL devices have dead clocks/relative time (< 1 billion seconds),
  # forcefully anchor the UI rendering to May 1st, 2024 so it doesn't look like 1970.
  if (ref_start < 1e9) {
    ref_start <- as.numeric(as.POSIXct("2024-05-01 12:00:00", tz = TZ))
  }

  # Unified device epocher: elapsed from device start, placed into reference timeline
  # bin = floor((elapsed + off_sec) / EPOCH_SEC) * EPOCH_SEC
  # → all devices land on the same global 5-s grid regardless of off_sec value
  device_ep <- function(df, off_sec, label) {
    if (is.null(df) || nrow(df) == 0) return(NULL)
    t_num   <- as.numeric(df$timestamp)
    elapsed <- t_num - min(t_num, na.rm = TRUE)
    bin     <- floor((elapsed + off_sec) / EPOCH_SEC) * EPOCH_SEC
    tibble(bin, vm = sqrt(rowSums(df[c("ax","ay","az")]^2, na.rm = TRUE))) %>%
      group_by(bin) %>% summarise(vm = mean(vm, na.rm = TRUE), .groups = "drop") %>%
      mutate(t      = as.POSIXct(ref_start + bin, origin = "1970-01-01", tz = TZ),
             device = label) %>%
      select(t, vm, device)
  }

  ag_ep <- device_ep(ag_src,            off$offset_actigraph_sec, "ActiGraph")
  em_ep <- device_ep(d$emotibit_accel,  off$offset_emotibit_sec,  "EmotiBit")
  bg_ep <- device_ep(d$bangle_accel,    off$offset_bangle_sec,    "Bangle")

  # Vyntus: timestamp is already elapsed seconds from test start
  vn_ep <- NULL
  if (!is.null(d$vyntus)) {
    vn_ep <- d$vyntus %>%
      mutate(t = as.POSIXct(ref_start + timestamp + off$offset_vyntus_sec,
                             origin = "1970-01-01", tz = TZ)) %>%
      select(t, hr_polar, vo2_per_kg) %>%
      filter(!is.na(hr_polar) | !is.na(vo2_per_kg))
  }

  list(ag = ag_ep, em = em_ep, bg = bg_ep, vn = vn_ep)
}

# Compute pairwise correlations from epoch data
compute_pairwise_r <- function(eps) {
  safe_r <- function(a, b) {
    if (is.null(a) || is.null(b)) return(NA_real_)
    merged <- inner_join(a %>% select(t, vm), b %>% select(t, vm), by = "t",
                         suffix = c("_a", "_b"))
    if (nrow(merged) < 5) return(NA_real_)
    round(safe_cor(merged$vm_a, merged$vm_b), 3)
  }
  list(
    ag_em = safe_r(eps$ag, eps$em),
    ag_bg = safe_r(eps$ag, eps$bg),
    em_bg = safe_r(eps$em, eps$bg)
  )
}

# =============================================================================
# INITIALISE trim_windows.csv if not present
# =============================================================================
trim_file <- "data/processed/trim_windows.csv"
if (!file.exists(trim_file)) {
  write.csv(
    data.frame(subject_id = as.character(subjects), start_time = NA_character_,
               end_time = NA_character_, alignment_method = "auto",
               confirmed = FALSE, notes = NA_character_,
               stringsAsFactors = FALSE),
    trim_file, row.names = FALSE
  )
}
trim_init <- read_csv_safe(trim_file)
if (is.null(trim_init)) {
  trim_init <- data.frame(subject_id = as.character(subjects), start_time = NA_character_,
                          end_time = NA_character_, alignment_method = "auto",
                          confirmed = FALSE, notes = NA_character_,
                          stringsAsFactors = FALSE)
}

# =============================================================================
# SHINY UI
# =============================================================================
ui <- fluidPage(
  tags$head(
    tags$style(HTML("
      .needs-review { color: #CC0000; font-weight: bold; }
      .sidebar-section { margin-top: 12px; padding-top: 8px; border-top: 1px solid #ddd; }
      .cor-display { font-family: monospace; font-size: 13px; background: #f5f5f5;
                     padding: 6px 8px; border-radius: 4px; margin-top: 6px; }
      .save-status  { color: #007700; font-size: 13px; margin-top: 6px; }
      .progress-lbl { font-weight: bold; color: #444; }
      #sidebar_toggle_btn { font-size: 11px; padding: 2px 7px; }
    ")),
    tags$script(HTML("
      function toggleSidebar() {
        var sidebar = document.getElementById('sidebar_col');
        var main    = document.getElementById('main_col');
        var btn     = document.getElementById('sidebar_toggle_btn');
        if (sidebar.style.display !== 'none') {
          sidebar.style.display = 'none';
          main.className = 'col-sm-12';
          btn.innerHTML  = '&#9654; Show controls';
        } else {
          sidebar.style.display = '';
          main.className = 'col-sm-9';
          btn.innerHTML  = '&#9664; Hide controls';
        }
      }
    "))
  ),

  titlePanel("Multi-device Accelerometry — Alignment & Trim"),

  tags$div(class = "row",
    # ---- Sidebar -----------------------------------------------------------
    tags$div(class = "col-sm-3", id = "sidebar_col",
      style = "overflow-y: auto; max-height: calc(100vh - 80px);",
      tags$div(class = "well",

      # ---- Subject selection ------------------------------------------------
      h4("Subject"),
      uiOutput("subject_selector"),
      div(class = "progress-lbl", textOutput("progress_label")),
      fluidRow(
        column(6, actionButton("btn_prev", "< Prev", width = "100%")),
        column(6, actionButton("btn_next", "Next >", width = "100%"))
      ),

      # ---- Device visibility -----------------------------------------------
      div(class = "sidebar-section",
        h4("Device visibility"),
        checkboxGroupInput("show_devices", NULL,
          choices  = c("ActiGraph", "EmotiBit", "Bangle"),
          selected = c("ActiGraph", "EmotiBit", "Bangle")),
        checkboxGroupInput("show_physio", NULL,
          choices  = c("HR (Polar)"),
          selected = c("HR (Polar)"))
      ),

      # ---- ActiGraph options -----------------------------------------------
      div(class = "sidebar-section",
        h4("ActiGraph options"),
        checkboxInput("ag_excluded", "Exclude from analysis", value = FALSE),
        conditionalPanel("!input.ag_excluded",
          checkboxInput("show_ag_crop", "Crop recording range", value = FALSE),
          conditionalPanel("input.show_ag_crop",
            p(em("Narrow the AG timeline to the test period"),
              style = "font-size:11px;margin:0 0 4px"),
            uiOutput("ag_crop_start_ui"),
            uiOutput("ag_crop_end_ui"),
            actionButton("btn_apply_ag_crop", "Apply crop", width = "100%",
                         style = "margin-top:4px")
          )
        )
      ),

      # ---- Zoom / view window ----------------------------------------------
      div(class = "sidebar-section",
        h4("Zoom view"),
        p(em("Controls the visible time window — does not affect trim or analysis"),
          style = "font-size:12px;margin:0 0 6px"),
        uiOutput("zoom_start_ui"),
        uiOutput("zoom_end_ui"),
        actionButton("btn_crop_view",  "Crop view to trim window", width = "100%",
                     style = "margin-bottom:4px"),
        actionButton("btn_reset_zoom", "Reset view to full recording", width = "100%")
      ),

      # ---- Trim controls ---------------------------------------------------
      div(class = "sidebar-section",
        h4("Trim window"),
        p(em("Blue shaded region = analysis interval"), style = "font-size:12px;margin:0 0 6px"),
        uiOutput("trim_start_ui"),
        uiOutput("trim_end_ui")
      ),

      # ---- Manual offsets -------------------------------------------------
      div(class = "sidebar-section",
        h4("Manual offset adjustment (seconds)"),
        p(em("Positive = device starts later than ActiGraph"),
          style = "font-size:11px; margin: 0 0 6px"),
        div(style = "color:#aaa; font-size:12px;", "ActiGraph: reference (fixed at 0)"),
        numericInput("off_em", "EmotiBit offset (s):", value = 0, step = 1),
        numericInput("off_bg", "Bangle offset (s):",   value = 0, step = 1),
        numericInput("off_vn", "Vyntus offset (s):",   value = 0, step = 1),
        actionButton("btn_apply", "Apply offsets", class = "btn-primary", width = "100%"),
        div(class = "cor-display", textOutput("live_cors"))
      ),

      # ---- Save ------------------------------------------------------------
      div(class = "sidebar-section",
        h4("Confirm subject"),
        textAreaInput("notes_input", "Notes (optional):", rows = 2, value = ""),
        actionButton("btn_save", "Confirm and save", class = "btn-success", width = "100%"),
        div(class = "save-status", textOutput("save_status"))
      )
      )   # /well
    ),  # /sidebar_col

    # ---- Main panel --------------------------------------------------------
    tags$div(class = "col-sm-9", id = "main_col",
      div(style = "margin-bottom: 4px;",
        tags$button(id = "sidebar_toggle_btn", onclick = "toggleSidebar()",
                    class = "btn btn-xs btn-default",
                    HTML("&#9664; Hide controls"))
      ),
      plotlyOutput("plot_full", height = "600px")
    )
  )  # /row
)

# =============================================================================
# SHINY SERVER
# =============================================================================
server <- function(input, output, session) {

  # ---- Reactive state -------------------------------------------------------
  rv <- reactiveValues(
    sid            = subjects[1],
    offsets        = offsets_df,
    trim_wins      = trim_init,
    eps            = NULL,     # current epoch data (after offsets applied)
    trim_start_val = NULL,     # numeric POSIX for current subject's trim start
    trim_end_val   = NULL,     # numeric POSIX for current subject's trim end
    save_msg       = "",
    ag_excluded    = FALSE,    # TRUE = exclude AG from plot and Step 3
    ag_crop        = list(t_start = NULL, t_end = NULL)  # NULL = no crop
  )

  # Load state for new subject
  load_subject <- function(sid) {
    sid <- as.character(sid)
    rv$sid <- sid

    # Load offsets — first try saved CSV, fall back to auto-computed values
    off_saved <- read_csv_safe("data/processed/alignment_offsets.csv")
    if (!is.null(off_saved) && sid %in% off_saved$subject_id) {
      off <- off_saved[off_saved$subject_id == sid, ]
    } else {
      off <- rv$offsets[rv$offsets$subject_id == sid, ]
    }
    updateNumericInput(session, "off_em", value = off$offset_emotibit_sec[1])
    updateNumericInput(session, "off_bg", value = off$offset_bangle_sec[1])
    updateNumericInput(session, "off_vn", value = off$offset_vyntus_sec[1])

    # Load saved AG options (exclusion + crop) for this subject
    ag_opts    <- read_csv_safe("data/processed/ag_options.csv")
    ag_opt_row <- if (!is.null(ag_opts) && sid %in% ag_opts$subject_id)
      ag_opts[ag_opts$subject_id == sid, ] else NULL

    ag_exc <- if (!is.null(ag_opt_row)) isTRUE(ag_opt_row$ag_excluded[1]) else FALSE
    ag_cs  <- if (!is.null(ag_opt_row) && !is.na(ag_opt_row$ag_crop_start[1]))
      as.numeric(as.POSIXct(ag_opt_row$ag_crop_start[1], tz = TZ)) else NULL
    ag_ce  <- if (!is.null(ag_opt_row) && !is.na(ag_opt_row$ag_crop_end[1]))
      as.numeric(as.POSIXct(ag_opt_row$ag_crop_end[1], tz = TZ)) else NULL

    rv$ag_excluded <- ag_exc
    rv$ag_crop     <- list(t_start = ag_cs, t_end = ag_ce)

    updateCheckboxInput(session, "ag_excluded",  value = ag_exc)
    updateCheckboxInput(session, "show_ag_crop", value = !is.null(ag_cs))

    # Compute epoch data for this subject using current in-memory offsets + AG options
    eps <- get_aligned_epochs(sid, rv$offsets,
                              ag_excluded = ag_exc,
                              ag_crop     = list(t_start = ag_cs, t_end = ag_ce))

    tr    <- eps_trange(eps)
    t_min <- tr$t_min
    t_max <- tr$t_max

    # Load saved trim window — re-read from disk so navigation always gets latest saved values
    tw_disk <- read_csv_safe("data/processed/trim_windows.csv")
    tw <- if (!is.null(tw_disk) && sid %in% tw_disk$subject_id)
            tw_disk[tw_disk$subject_id == sid, ]
          else
            rv$trim_wins[rv$trim_wins$subject_id == sid, ]

    saved_start <- if (nrow(tw) > 0 && !is.na(tw$start_time[1]))
      as.numeric(as.POSIXct(tw$start_time[1], tz = TZ)) else t_min
    saved_end   <- if (nrow(tw) > 0 && !is.na(tw$end_time[1]))
      as.numeric(as.POSIXct(tw$end_time[1], tz = TZ)) else t_max
    saved_notes <- if (nrow(tw) > 0 && !is.na(tw$notes[1])) tw$notes[1] else ""

    # Store trim values in rv BEFORE setting rv$eps so renderUI picks them up
    rv$trim_start_val <- saved_start
    rv$trim_end_val   <- saved_end
    rv$eps            <- eps

    updateTextAreaInput(session, "notes_input", value = saved_notes)

    # Sync trim sliders (min/max from this subject's data, value from saved or default)
    updateSliderInput(session, "trim_start",
                      min = t_min, max = t_max, value = saved_start, step = 5)
    updateSliderInput(session, "trim_end",
                      min = t_min, max = t_max, value = saved_end,   step = 5)

    # Reset zoom to full range for new subject
    updateSliderInput(session, "zoom_start",
                      min = t_min, max = t_max, value = t_min, step = 5)
    updateSliderInput(session, "zoom_end",
                      min = t_min, max = t_max, value = t_max, step = 5)
  }

  # Helper: safe [t_min, t_max] from epoch list — returns (0, 3600) when no data
  eps_trange <- function(eps) {
    all_t <- unlist(lapply(list(eps$ag, eps$em, eps$bg),
                           function(e) if (!is.null(e) && nrow(e) > 0)
                             as.numeric(e$t) else NULL))
    finite_t <- all_t[is.finite(all_t)]
    if (length(finite_t) == 0) return(list(t_min = 0, t_max = 3600))
    list(t_min = min(finite_t), t_max = max(finite_t))
  }

  # Dynamic subject selector (flag review subjects in red)
  output$subject_selector <- renderUI({
    needs <- rv$offsets %>% filter(needs_review) %>% pull(subject_id)
    choices <- subjects
    names(choices) <- ifelse(subjects %in% needs,
                             paste0("\u26A0 ", subjects, " (review)"),
                             subjects)
    selectInput("subject_sel", NULL, choices = choices, selected = isolate(rv$sid))
  })

  output$progress_label <- renderText({
    n_conf <- sum(rv$trim_wins$confirmed == TRUE, na.rm = TRUE)
    sprintf("%d / %d subjects confirmed", n_conf, length(subjects))
  })

  # Dynamic trim sliders (need to know time range per subject)
  output$trim_start_ui <- renderUI({
    eps   <- rv$eps
    tr    <- eps_trange(eps)
    t_min <- tr$t_min; t_max <- tr$t_max
    # Use saved/restored value if available, otherwise default to recording start
    init_val <- if (!is.null(rv$trim_start_val)) rv$trim_start_val else t_min
    init_val <- max(t_min, min(t_max, init_val))   # clamp to valid range
    sliderInput("trim_start", "Start (drag or use arrow keys):",
                min = t_min, max = t_max, value = init_val,
                step = 5, width = "100%",
                timeFormat = "%H:%M:%S", timezone = format(as.POSIXct(Sys.time(), tz=TZ), "%z"))
  })
  output$trim_end_ui <- renderUI({
    eps   <- rv$eps
    tr    <- eps_trange(eps)
    t_min <- tr$t_min; t_max <- tr$t_max
    # Use saved/restored value if available, otherwise default to recording end
    init_val <- if (!is.null(rv$trim_end_val)) rv$trim_end_val else t_max
    init_val <- max(t_min, min(t_max, init_val))   # clamp to valid range
    sliderInput("trim_end", "End:",
                min = t_min, max = t_max, value = init_val,
                step = 5, width = "100%",
                timeFormat = "%H:%M:%S", timezone = format(as.POSIXct(Sys.time(), tz=TZ), "%z"))
  })

  output$zoom_start_ui <- renderUI({
    eps   <- rv$eps
    tr    <- eps_trange(eps)
    t_min <- tr$t_min; t_max <- tr$t_max
    sliderInput("zoom_start", "From:",
                min = t_min, max = t_max, value = t_min,
                step = 5, width = "100%",
                timeFormat = "%H:%M:%S", timezone = format(as.POSIXct(Sys.time(), tz=TZ), "%z"))
  })
  output$zoom_end_ui <- renderUI({
    eps   <- rv$eps
    tr    <- eps_trange(eps)
    t_min <- tr$t_min; t_max <- tr$t_max
    sliderInput("zoom_end", "To:",
                min = t_min, max = t_max, value = t_max,
                step = 5, width = "100%",
                timeFormat = "%H:%M:%S", timezone = format(as.POSIXct(Sys.time(), tz=TZ), "%z"))
  })

  # Dynamic AG crop sliders (range = full AG recording for this subject)
  output$ag_crop_start_ui <- renderUI({
    d <- raw_data[[rv$sid]]
    if (is.null(d$actigraph) || nrow(d$actigraph) == 0) return(NULL)
    t_ag  <- as.numeric(d$actigraph$timestamp)
    t_min <- min(t_ag, na.rm = TRUE); t_max <- max(t_ag, na.rm = TRUE)
    init  <- if (!is.null(rv$ag_crop$t_start))
      max(t_min, min(t_max, rv$ag_crop$t_start)) else t_min
    sliderInput("ag_crop_start", "Crop start:",
                min = t_min, max = t_max, value = init, step = 60,
                width = "100%",
                timeFormat = "%H:%M:%S",
                timezone = format(as.POSIXct(Sys.time(), tz = TZ), "%z"))
  })
  output$ag_crop_end_ui <- renderUI({
    d <- raw_data[[rv$sid]]
    if (is.null(d$actigraph) || nrow(d$actigraph) == 0) return(NULL)
    t_ag  <- as.numeric(d$actigraph$timestamp)
    t_min <- min(t_ag, na.rm = TRUE); t_max <- max(t_ag, na.rm = TRUE)
    init  <- if (!is.null(rv$ag_crop$t_end))
      max(t_min, min(t_max, rv$ag_crop$t_end)) else t_max
    sliderInput("ag_crop_end", "Crop end:",
                min = t_min, max = t_max, value = init, step = 60,
                width = "100%",
                timeFormat = "%H:%M:%S",
                timezone = format(as.POSIXct(Sys.time(), tz = TZ), "%z"))
  })

  # ---- Observers -----------------------------------------------------------
  observeEvent(input$subject_sel, { load_subject(input$subject_sel) })

  observeEvent(input$btn_prev, {
    idx <- which(subjects == rv$sid) - 1L
    if (idx >= 1) updateSelectInput(session, "subject_sel", selected = subjects[idx])
  })
  observeEvent(input$btn_next, {
    idx <- which(subjects == rv$sid) + 1L
    if (idx <= length(subjects)) updateSelectInput(session, "subject_sel", selected = subjects[idx])
  })

  observeEvent(input$btn_apply, {
    sid <- rv$sid
    rv$offsets <- rv$offsets %>%
      mutate(
        offset_emotibit_sec = if_else(subject_id == sid, as.numeric(input$off_em), offset_emotibit_sec),
        offset_bangle_sec   = if_else(subject_id == sid, as.numeric(input$off_bg), offset_bangle_sec),
        offset_vyntus_sec   = if_else(subject_id == sid, as.numeric(input$off_vn), offset_vyntus_sec),
        alignment_method    = if_else(subject_id == sid, "manual", alignment_method),
        manual_adjusted     = if_else(subject_id == sid, TRUE, manual_adjusted)
      )
    rv$eps <- get_aligned_epochs(sid, rv$offsets,
                                 ag_excluded = rv$ag_excluded, ag_crop = rv$ag_crop)
  })

  # Apply AG crop: store boundaries and recompute epochs
  observeEvent(input$btn_apply_ag_crop, {
    rv$ag_crop <- list(t_start = input$ag_crop_start, t_end = input$ag_crop_end)
    eps <- get_aligned_epochs(rv$sid, rv$offsets,
                              ag_excluded = rv$ag_excluded, ag_crop = rv$ag_crop)
    rv$eps <- eps
    tr <- eps_trange(eps)
    updateSliderInput(session, "trim_start", min = tr$t_min, max = tr$t_max)
    updateSliderInput(session, "trim_end",   min = tr$t_min, max = tr$t_max)
    updateSliderInput(session, "zoom_start", min = tr$t_min, max = tr$t_max, value = tr$t_min)
    updateSliderInput(session, "zoom_end",   min = tr$t_min, max = tr$t_max, value = tr$t_max)
  })

  # Toggle AG exclusion: immediately recompute epochs
  observeEvent(input$ag_excluded, {
    rv$ag_excluded <- input$ag_excluded
    eps <- get_aligned_epochs(rv$sid, rv$offsets,
                              ag_excluded = rv$ag_excluded, ag_crop = rv$ag_crop)
    rv$eps <- eps
    tr <- eps_trange(eps)
    updateSliderInput(session, "trim_start", min = tr$t_min, max = tr$t_max)
    updateSliderInput(session, "trim_end",   min = tr$t_min, max = tr$t_max)
    updateSliderInput(session, "zoom_start", min = tr$t_min, max = tr$t_max, value = tr$t_min)
    updateSliderInput(session, "zoom_end",   min = tr$t_min, max = tr$t_max, value = tr$t_max)
  }, ignoreInit = TRUE)

  # Crop view: set zoom window to current trim window (plus 5-second padding each side)
  observeEvent(input$btn_crop_view, {
    req(input$trim_start, input$trim_end)
    tr    <- eps_trange(rv$eps)
    t_min <- tr$t_min; t_max <- tr$t_max
    padded_start <- max(t_min, input$trim_start - 5)
    padded_end   <- min(t_max, input$trim_end   + 5)
    updateSliderInput(session, "zoom_start", value = padded_start)
    updateSliderInput(session, "zoom_end",   value = padded_end)
  })

  # Reset view: restore full recording range
  observeEvent(input$btn_reset_zoom, {
    eps   <- rv$eps
    all_t <- unlist(lapply(list(eps$ag, eps$em, eps$bg),
                           function(e) if (!is.null(e)) as.numeric(e$t) else NULL))
    t_min <- if (length(all_t)) min(all_t) else 0
    t_max <- if (length(all_t)) max(all_t) else 3600
    updateSliderInput(session, "zoom_start", value = t_min)
    updateSliderInput(session, "zoom_end",   value = t_max)
  })

  # Helper: safely write a trim row (base R, no type ambiguity)
  save_trim_row <- function(sid, start_time, end_time, method, notes) {
    path    <- "data/processed/trim_windows.csv"
    existing <- read_csv_safe(path)
    if (is.null(existing)) existing <- data.frame()
    existing <- existing[existing$subject_id != sid, ]
    new_row  <- data.frame(
      subject_id       = as.character(sid),
      start_time       = as.character(start_time),
      end_time         = as.character(end_time),
      alignment_method = as.character(method),
      confirmed        = TRUE,
      notes            = as.character(notes),
      stringsAsFactors = FALSE
    )
    write.csv(rbind(existing, new_row), path, row.names = FALSE)
    new_row    # return for updating rv
  }

  # Helper: save AG options (exclusion + crop) to ag_options.csv
  save_ag_options <- function(sid, ag_excluded, ag_crop) {
    path     <- "data/processed/ag_options.csv"
    existing <- read_csv_safe(path)
    if (is.null(existing)) existing <- data.frame()
    existing <- existing[existing$subject_id != sid, ]
    new_row  <- data.frame(
      subject_id    = as.character(sid),
      ag_excluded   = isTRUE(ag_excluded),
      ag_crop_start = if (!is.null(ag_crop$t_start))
        format(as.POSIXct(ag_crop$t_start, origin = "1970-01-01", tz = TZ),
               "%Y-%m-%d %H:%M:%S") else NA_character_,
      ag_crop_end   = if (!is.null(ag_crop$t_end))
        format(as.POSIXct(ag_crop$t_end, origin = "1970-01-01", tz = TZ),
               "%Y-%m-%d %H:%M:%S") else NA_character_,
      stringsAsFactors = FALSE
    )
    write.csv(rbind(existing, new_row), path, row.names = FALSE)
  }

  # Helper: safely write an offset row
  save_offset_row <- function(off_row) {
    path     <- "data/processed/alignment_offsets.csv"
    existing <- read_csv_safe(path)
    if (is.null(existing)) existing <- data.frame()
    existing <- existing[existing$subject_id != off_row$subject_id[1], ]
    write.csv(rbind(existing, off_row), path, row.names = FALSE)
  }

  observeEvent(input$btn_save, {
    sid      <- as.character(rv$sid)
    ts_start <- as.POSIXct(input$trim_start, origin = "1970-01-01", tz = TZ)
    ts_end   <- as.POSIXct(input$trim_end,   origin = "1970-01-01", tz = TZ)
    meth     <- rv$offsets$alignment_method[rv$offsets$subject_id == sid][1]

    # Save trim window to disk
    new_tw <- save_trim_row(
      sid,
      format(ts_start, "%Y-%m-%d %H:%M:%S"),
      format(ts_end,   "%Y-%m-%d %H:%M:%S"),
      meth,
      input$notes_input
    )

    # Save offsets to disk
    off_row <- as.data.frame(rv$offsets[rv$offsets$subject_id == sid, ],
                              stringsAsFactors = FALSE)
    off_row$subject_id <- as.character(off_row$subject_id)
    save_offset_row(off_row)

    # Save AG options (exclusion + crop) to disk
    save_ag_options(sid, rv$ag_excluded, rv$ag_crop)

    # Update in-memory trim_wins (keep subject_id as character)
    rv$trim_wins <- {
      base <- rv$trim_wins[rv$trim_wins$subject_id != sid, ]
      new_tw$subject_id <- as.character(new_tw$subject_id)
      rbind(base, new_tw)
    }

    # Build save message
    n_conf  <- sum(rv$trim_wins$confirmed == TRUE, na.rm = TRUE)
    n_total <- length(subjects)
    if (n_conf >= n_total) {
      rv$save_msg <- sprintf("All %d subjects confirmed. You can close the app.", n_total)
    } else {
      rv$save_msg <- sprintf("Subject %s saved. %d of %d confirmed.",
                             sid, n_conf, n_total)
    }

    # Auto-advance to next unconfirmed subject (skip already confirmed)
    unconf <- rv$trim_wins$subject_id[!rv$trim_wins$confirmed %in% TRUE]
    unconf <- as.character(unconf[!is.na(unconf)])
    if (length(unconf)) load_subject(unconf[1])
  })

  output$save_status <- renderText(rv$save_msg)

  # ---- Live correlation display -------------------------------------------
  output$live_cors <- renderText({
    req(rv$eps)
    cors <- compute_pairwise_r(rv$eps)
    fmt  <- function(r) if (is.na(r)) "NA" else sprintf("%.3f", r)
    sprintf("AG\u2013EM: %s  |  AG\u2013BG: %s  |  EM\u2013BG: %s",
            fmt(cors$ag_em), fmt(cors$ag_bg), fmt(cors$em_bg))
  })

  # ---- Build plotly figure for given time window ---------------------------
  make_plot <- function(eps, trim_start_t, trim_end_t, t_from = NULL, t_to = NULL,
                        view_from = NULL, view_to = NULL,
                        show_devices = NULL, show_physio = NULL, title = NULL) {
    p <- plot_ly(source = "main_plot")

    # VM traces
    if (!is.null(eps$ag) && ("ActiGraph" %in% show_devices)) {
      d <- eps$ag
      if (!is.null(t_from)) d <- filter(d, t >= t_from & t <= t_to)
      p <- add_lines(p, data = d, x = ~t, y = ~vm, name = "ActiGraph VM",
                     line = list(color = COL$ag, width = 2))
    }
    if (!is.null(eps$em) && ("EmotiBit" %in% show_devices)) {
      d <- eps$em
      if (!is.null(t_from)) d <- filter(d, t >= t_from & t <= t_to)
      p <- add_lines(p, data = d, x = ~t, y = ~vm, name = "EmotiBit VM",
                     line = list(color = COL$em, width = 2))
    }
    if (!is.null(eps$bg) && ("Bangle" %in% show_devices)) {
      d <- eps$bg
      if (!is.null(t_from)) d <- filter(d, t >= t_from & t <= t_to)
      p <- add_lines(p, data = d, x = ~t, y = ~vm, name = "Bangle VM",
                     line = list(color = COL$bg, width = 2))
    }

    # Physio traces (secondary y-axis)
    if (!is.null(eps$vn)) {
      vn <- eps$vn
      if (!is.null(t_from)) vn <- filter(vn, t >= t_from & t <= t_to)
      if ("HR (Polar)" %in% show_physio && !is.null(vn) && any(!is.na(vn$hr_polar))) {
        p <- add_lines(p, data = vn, x = ~t, y = ~hr_polar, name = "HR (bpm)",
                       yaxis = "y2",
                       line = list(color = COL$hr, width = 2, dash = "dash"))
      }
    }

    # Trim shading and vertical lines
    p <- layout(p,
      title  = list(text = title, font = list(size = 13)),
      xaxis  = if (!is.null(view_from) && !is.null(view_to))
                 list(title = "", type = "date",
                      range = c(format(view_from, "%Y-%m-%dT%H:%M:%S"),
                                format(view_to,   "%Y-%m-%dT%H:%M:%S")))
               else
                 list(title = "", type = "date"),
      yaxis  = list(title = "VM (g)", side = "left"),
      yaxis2 = list(title = "HR (bpm)",
                    overlaying = "y", side = "right",
                    showgrid = FALSE),
      legend = list(orientation = "h", x = 0, y = -0.25),
      shapes = list(
        # Shaded trim region
        list(type = "rect", layer = "below",
             x0 = trim_start_t, x1 = trim_end_t,
             y0 = 0, y1 = 1, yref = "paper",
             fillcolor = COL$trim_fill,
             line = list(width = 0)),
        # Trim start line
        list(type = "line", x0 = trim_start_t, x1 = trim_start_t,
             y0 = 0, y1 = 1, yref = "paper",
             line = list(color = "#4488CC", width = 2, dash = "dash")),
        # Trim end line
        list(type = "line", x0 = trim_end_t, x1 = trim_end_t,
             y0 = 0, y1 = 1, yref = "paper",
             line = list(color = "#4488CC", width = 2, dash = "dash"))
      ),
      hovermode = "x unified",
      margin    = list(t = 30, b = 60)
    ) %>%
      config(editable = TRUE, displayModeBar = TRUE,
             modeBarButtonsToRemove = list("lasso2d", "select2d")) %>%
      event_register("plotly_relayout")
    p
  }

  # Capture drag events on the full plot to sync trim sliders
  observeEvent(event_data("plotly_relayout", source = "main_plot"), {
    ev <- event_data("plotly_relayout", source = "main_plot")
    if (!is.null(ev)) {
      s0 <- ev[["shapes[1].x0"]]  # trim start line (index 1, after rect at 0)
      s1 <- ev[["shapes[2].x0"]]  # trim end line   (index 2)
      if (!is.null(s0)) {
        new_t <- tryCatch(as.numeric(as.POSIXct(s0 / 1000, origin = "1970-01-01", tz = TZ)),
                          error = function(e) NULL)
        if (!is.null(new_t)) updateSliderInput(session, "trim_start", value = new_t)
      }
      if (!is.null(s1)) {
        new_t <- tryCatch(as.numeric(as.POSIXct(s1 / 1000, origin = "1970-01-01", tz = TZ)),
                          error = function(e) NULL)
        if (!is.null(new_t)) updateSliderInput(session, "trim_end", value = new_t)
      }
    }
  })

  # ---- Render plots --------------------------------------------------------
  output$plot_full <- renderPlotly({
    req(rv$eps, input$trim_start, input$trim_end)
    ts <- as.POSIXct(input$trim_start, origin = "1970-01-01", tz = TZ)
    te <- as.POSIXct(input$trim_end,   origin = "1970-01-01", tz = TZ)

    vf <- if (!is.null(input$zoom_start))
      as.POSIXct(input$zoom_start, origin = "1970-01-01", tz = TZ) else NULL
    vt <- if (!is.null(input$zoom_end))
      as.POSIXct(input$zoom_end,   origin = "1970-01-01", tz = TZ) else NULL

    make_plot(rv$eps, ts, te,
              view_from    = vf,
              view_to      = vt,
              show_devices = input$show_devices,
              show_physio  = input$show_physio,
              title = sprintf("Subject %s — Full recording", rv$sid))
  })

  # Initialise first subject (must be inside observe so rv is accessible)
  observe({
    isolate(load_subject(subjects[1]))
  })
}

# =============================================================================
# LAUNCH
# =============================================================================
shiny::runApp(shinyApp(ui = ui, server = server), launch.browser = TRUE)
