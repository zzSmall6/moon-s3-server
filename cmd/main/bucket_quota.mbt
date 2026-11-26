///|
fn parse_bucket_quotas(document : Json) -> Map[String, Int64] raise {
  let fields = match document {
    Object(fields) if fields.length() <= 128 => fields
    _ => raise Failure("Expected at most 128 bucket quotas")
  }
  let quotas : Map[String, Int64] = Map([])
  for bucket, value in fields {
    if !@core.valid_bucket_name(bucket) ||
      bucket == "metrics" ||
      bucket == "healthz" {
      raise Failure("Invalid quota bucket")
    }
    quotas[bucket] = match value {
      Number(number, ..) if number >= 0.0 &&
        number <= 5497558138880.0 &&
        number == number.to_int64().to_double() => number.to_int64()
      _ => raise Failure("Invalid bucket quota bytes")
    }
  }
  quotas
}

///|
async fn upload_payload_bytes(
  config : Config,
  bucket : String,
  identifier : String,
) -> Int64 {
  let directory = upload_dir(config, bucket, identifier)
  let mut size = 0L
  if @fs.exists(directory) {
    for entry in @fs.readdir(directory, include_hidden=false) {
      if entry.strip_prefix("part.") is Some(number) &&
        version_number(number.to_owned()) is Some(number) &&
        number >= 1L &&
        number <= 10000L {
        size += @fs.file_size(directory + "/" + entry)
      }
    }
  }
  size
}

///|
async fn bucket_usage(config : Config, bucket : String) -> Int64 {
  if !@fs.exists(objects_dir(config, bucket)) {
    return 0L
  }
  recover_bucket(config, bucket)
  let keys : Map[String, Bool] = Map([])
  for entry in @fs.readdir(objects_dir(config, bucket), include_hidden=false) {
    if entry.has_suffix(".object") {
      keys[storage_key(config, bucket, entry[:entry.length() - 7].to_owned())] = true
    }
  }
  let history = bucket_dir(config, bucket) + "/.versions"
  if @fs.exists(history) {
    for entry in @fs.readdir(history, include_hidden=false) {
      keys[storage_key(config, bucket, entry)] = true
    }
  }
  let mut used = 0L
  for key, _ in keys {
    for version in all_key_versions(config, bucket, key) {
      if !version.marker {
        used += version.size
      }
    }
  }
  let uploads = bucket_dir(config, bucket) + "/.uploads"
  if @fs.exists(uploads) {
    for identifier in @fs.readdir(uploads, include_hidden=false) {
      if valid_upload_id(identifier) {
        used += upload_payload_bytes(config, bucket, identifier)
      }
    }
  }
  used
}

///|
fn quota_allows(used : Int64, projected : Int64, limit : Int64) -> Bool {
  projected >= 0L && (projected <= limit || projected < used)
}

///|
async fn check_quota(
  config : Config,
  bucket : String,
  used : Int64,
  projected : Int64,
  conn : ResponseConnection,
) -> Bool {
  let limit = match config.bucket_quotas.get(bucket) {
    Some(limit) => limit
    None => return true
  }
  if quota_allows(used, projected, limit) {
    return true
  }
  send_error(
    conn,
    403,
    "QuotaExceeded",
    "The write would exceed this bucket's retained payload quota.",
    config.cors_origin,
  )
  false
}

///|
async fn check_object_quota(
  config : Config,
  bucket : String,
  key : String,
  size : Int64,
  conn : ResponseConnection,
  released~ : Int64 = 0L,
) -> Bool {
  if !config.bucket_quotas.contains(bucket) {
    return true
  }
  let used = bucket_usage(config, bucket)
  let status = versioning_status(config, bucket)
  let mut replaced = 0L
  for version in all_key_versions(config, bucket, key) {
    if status == "" || (status == "Suspended" && version.id == "null") {
      replaced += version.size
    }
  }
  check_quota(config, bucket, used, used - replaced - released + size, conn)
}

///|
async fn quota_metrics(config : Config) -> String {
  let mut text = "# TYPE moon_s3_bucket_used_bytes gauge\n# TYPE moon_s3_bucket_quota_bytes gauge\n# TYPE moon_s3_bucket_quota_remaining_bytes gauge\n"
  let buckets = config.bucket_quotas.keys().to_array()
  buckets.sort()
  for bucket in buckets {
    let limit = config.bucket_quotas.get(bucket).unwrap()
    let used = bucket_usage(config, bucket)
    let remaining = if used >= limit { 0L } else { limit - used }
    text += "moon_s3_bucket_used_bytes{bucket=\"\{bucket}\"} \{used}\nmoon_s3_bucket_quota_bytes{bucket=\"\{bucket}\"} \{limit}\nmoon_s3_bucket_quota_remaining_bytes{bucket=\"\{bucket}\"} \{remaining}\n"
  }
  text
}
