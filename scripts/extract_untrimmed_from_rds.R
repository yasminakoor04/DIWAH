# Export untrimmed 5-second epochs for manually excluded subjects.

BAD_SUBJECTS <- c("2004", "2005", "2008", "2014", "2019", "2032")

normalize_subject <- function(x) {
  x <- as.character(x)
  x <- sub("^Diwah", "", x)
  trimws(x)
}

pick_first_col <- function(df, candidates) {
  hits <- intersect(candidates, names(df))
  if (length(hits) == 0) {
    return(NULL)
  }
  hits[[1]]
}

infer_device_name <- function(name_hint, df) {
  hint <- tolower(name_hint)
  if (grepl("acti", hint)) return("actigraph")
  if (grepl("bangle", hint)) return("bangle")
  if (grepl("emoti", hint)) return("emotibit")

  if ("device" %in% names(df)) {
    vals <- unique(tolower(as.character(df$device)))
    vals <- vals[!is.na(vals)]
    if (length(vals) > 0) {
      if (any(grepl("acti", vals))) return("actigraph")
      if (any(grepl("bangle", vals))) return("bangle")
      if (any(grepl("emoti", vals))) return("emotibit")
    }
  }

  NULL
}

as_epoch_5s <- function(ts) {
  sec <- as.numeric(ts)
  if (all(is.na(sec))) return(rep(as.POSIXct(NA), length(ts)))
  floored <- floor(sec / 5) * 5
  as.POSIXct(floored, origin = "1970-01-01", tz = "UTC")
}

compute_vm <- function(df) {
  vm_col <- pick_first_col(df, c("vm", "vm_mean", "vm_mean_raw", "magnitude", "acc_magnitude", "acc_magnitude_5s"))
  if (!is.null(vm_col)) {
    return(as.numeric(df[[vm_col]]))
  }

  x_col <- pick_first_col(df, c("x", "acc_x", "axis1", "X"))
  y_col <- pick_first_col(df, c("y", "acc_y", "axis2", "Y"))
  z_col <- pick_first_col(df, c("z", "acc_z", "axis3", "Z"))

  if (!is.null(x_col) && !is.null(y_col) && !is.null(z_col)) {
    x <- as.numeric(df[[x_col]])
    y <- as.numeric(df[[y_col]])
    z <- as.numeric(df[[z_col]])
    return(sqrt(x * x + y * y + z * z))
  }

  rep(NA_real_, nrow(df))
}

aggregate_device <- function(df, subject_hint = NULL, device_hint = NULL) {
  if (!is.data.frame(df) || nrow(df) == 0) return(NULL)

  subject_col <- pick_first_col(df, c("subject", "Subject", "id", "ID", "participant"))
  timestamp_col <- pick_first_col(df, c("timestamp", "Timestamp", "time", "Time", "datetime", "Datetime"))

  if (is.null(timestamp_col)) return(NULL)

  if (is.null(subject_col)) {
    if (is.null(subject_hint)) return(NULL)
    subject <- rep(normalize_subject(subject_hint), nrow(df))
  } else {
    subject <- normalize_subject(df[[subject_col]])
  }

  ts <- as.POSIXct(df[[timestamp_col]], tz = "UTC")
  if (all(is.na(ts))) {
    ts_num <- suppressWarnings(as.numeric(df[[timestamp_col]]))
    if (!all(is.na(ts_num))) {
      ts <- as.POSIXct(ts_num, origin = "1970-01-01", tz = "UTC")
    }
  }

  vm <- compute_vm(df)

  out <- data.frame(
    subject = subject,
    timestamp = as_epoch_5s(ts),
    vm = vm,
    stringsAsFactors = FALSE
  )

  out <- out[!is.na(out$subject) & out$subject != "" & !is.na(out$timestamp) & !is.na(out$vm), ]
  if (nrow(out) == 0) return(NULL)

  out <- out[out$subject %in% BAD_SUBJECTS, ]
  if (nrow(out) == 0) return(NULL)

  agg <- aggregate(vm ~ subject + timestamp, data = out, FUN = mean)

  device <- infer_device_name(ifelse(is.null(device_hint), "", device_hint), df)
  if (is.null(device)) return(NULL)

  colname <- paste0("vm_mean_", device)
  names(agg)[names(agg) == "vm"] <- colname
  agg
}

merge_wide <- function(existing, incoming) {
  if (is.null(existing)) return(incoming)
  if (is.null(incoming)) return(existing)
  merge(existing, incoming, by = c("subject", "timestamp"), all = TRUE)
}

extract_from_object <- function(obj, subject_hint = NULL, name_hint = "") {
  if (is.data.frame(obj)) {
    return(aggregate_device(obj, subject_hint = subject_hint, device_hint = name_hint))
  }

  if (is.list(obj)) {
    merged <- NULL
    nm <- names(obj)
    for (i in seq_along(obj)) {
      child <- obj[[i]]
      child_name <- if (!is.null(nm) && nzchar(nm[[i]])) nm[[i]] else ""
      child_subject <- subject_hint
      if (!is.null(nm) && nzchar(nm[[i]]) && grepl("^[0-9]{4}$", nm[[i]])) {
        child_subject <- nm[[i]]
      }
      child_res <- extract_from_object(child, subject_hint = child_subject, name_hint = child_name)
      merged <- merge_wide(merged, child_res)
    }
    return(merged)
  }

  NULL
}

run_untrimmed_export <- function(rds_path, output_csv) {
  raw_obj <- readRDS(rds_path)

  wide <- extract_from_object(raw_obj)
  if (is.null(wide) || nrow(wide) == 0) {
    stop("Could not extract untrimmed epochs from raw_data.rds")
  }

  wide <- wide[wide$subject %in% BAD_SUBJECTS, ]
  wide <- wide[order(wide$subject, wide$timestamp), ]

  write.csv(wide, output_csv, row.names = FALSE)
  cat(sprintf("Wrote %d rows to %s\n", nrow(wide), output_csv))
}
