///|
#borrow(path)
extern "C" fn available_disk_bytes_ffi(path : Bytes) -> Int64 = "moon_s3_available_disk_bytes"

///|
fn available_disk_bytes(config : Config) -> Int64 {
  available_disk_bytes_ffi(@utf8.encode(config.root + "\u0000"))
}

///|
fn disk_space_allows(
  available : Int64,
  pending : Int64,
  minimum : Int64,
  required : Int64,
) -> Bool {
  available >= 0L &&
  pending >= 0L &&
  required >= 0L &&
  available >= minimum &&
  available - minimum >= pending &&
  available - minimum - pending >= required
}

///|
async fn check_upload_disk(
  config : Config,
  required : Int64,
  conn : ResponseConnection,
) -> Bool {
  if disk_space_allows(
      available_disk_bytes(config),
      config.runtime.disk_writes_pending,
      config.min_free_disk_bytes,
      required,
    ) {
    return true
  }
  config.runtime.disk_rejections += 1L
  conn.trace.close_after = true
  send_error(
    conn,
    507,
    "InsufficientStorage",
    "Upload cannot preserve the configured free disk reserve, or disk capacity is unavailable.",
    config.cors_origin,
  )
  false
}

///|
fn disk_metrics(config : Config) -> String {
  "# TYPE moon_s3_disk_available_bytes gauge\nmoon_s3_disk_available_bytes \{available_disk_bytes(config)}\n" +
  "# TYPE moon_s3_disk_min_free_bytes gauge\nmoon_s3_disk_min_free_bytes \{config.min_free_disk_bytes}\n" +
  "# TYPE moon_s3_upload_disk_rejections_total counter\nmoon_s3_upload_disk_rejections_total \{config.runtime.disk_rejections}\n"
}
