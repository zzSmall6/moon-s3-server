///|
fn bucket_permission(
  grants : Map[String, Bool],
  bucket : String,
  write~ : Bool,
) -> Bool {
  match grants.get(bucket) {
    Some(can_write) => !write || can_write
    None => false
  }
}

///|
fn request_permission(
  config : Config,
  request : @http.Request,
  raw_path : String,
  params : Array[@core.QueryParam],
) -> Bool {
  let credentials = match config.credentials {
    None => return true
    Some(credentials) => credentials
  }
  let access = if has_query_auth(params) {
    match @core.query_value(params, "X-Amz-Credential") {
      Some(value) => value.split("/").next().unwrap_or("").to_owned()
      None => return false
    }
  } else {
    match @core.parse_authorization(header(request.headers, "authorization")) {
      Some(auth) => auth.access_key
      None => return false
    }
  }
  let grants = match credentials.get(access) {
    Some({ permissions: None, .. }) => return true
    Some({ permissions: Some(grants), .. }) => grants
    None => return false
  }
  let (bucket, key) = @core.split_bucket_key(raw_path)
  let bucket = match bucket {
    Some(bucket) if bucket != "metrics" && bucket != "healthz" => bucket
    _ => return false
  }
  if params.any(param => ["policy", "cors", "versioning"].contains(param.name)) {
    return false
  }
  let write = match request.meth {
    Get | Head => false
    Put | Delete if key is Some(_) => true
    Post if key is Some(_) && is_multipart_request(params) => true
    Post if key is None && @core.query_value(params, "delete") is Some(_) =>
      true
    _ => return false
  }
  if !bucket_permission(grants, bucket, write~) {
    return false
  }
  if request.headers.contains(@http.CaseInsensitiveString("x-amz-copy-source")) {
    let (source, _, _) = match
      parse_versioned_copy_source(header(request.headers, "x-amz-copy-source")) {
      Some(source) => source
      None => return false
    }
    return bucket_permission(grants, source, write=false)
  }
  true
}
