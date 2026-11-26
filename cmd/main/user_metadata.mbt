///|
fn valid_user_metadata(values : Map[String, String]) -> Bool {
  let mut size = 0
  for name, value in values {
    if name.is_empty() ||
      name.length() > 128 ||
      !name
      .to_array()
      .all(character => {
        (character >= 'a' && character <= 'z') ||
        (character >= '0' && character <= '9') ||
        "!#$%&'*+-.^_`|~".contains(character.to_string())
      }) ||
      value
      .to_array()
      .any(character => character.to_int() < 32 || character.to_int() > 126) {
      return false
    }
    size += @utf8.encode(name).length() + @utf8.encode(value).length()
    if size > 2048 {
      return false
    }
  }
  true
}

///|
fn user_metadata_values(text : String) -> Map[String, String] raise {
  if text.is_empty() {
    return Map([])
  }
  if @utf8.encode(text).length() > 16384 {
    raise Failure("User metadata record is too large")
  }
  let fields = match
    @json.parse(text, max_nesting_depth=2, reject_duplicate_keys=true) {
    Object(fields) => fields
    _ => raise Failure("Invalid user metadata record")
  }
  let values : Map[String, String] = Map([])
  for name, value in fields {
    values[name] = match value {
      String(value) => value
      _ => raise Failure("Invalid user metadata value")
    }
  }
  if !valid_user_metadata(values) {
    raise Failure("Invalid user metadata record")
  }
  values
}

///|
fn request_user_metadata(request : @http.Request) -> String? {
  let fields : Map[String, Json] = Map([])
  let values : Map[String, String] = Map([])
  for name, value in request.headers {
    let name = name.to_string().to_lower()
    if name.strip_prefix("x-amz-meta-") is Some(suffix) {
      values[suffix.to_owned()] = value
      fields[suffix.to_owned()] = Json::string(value)
    }
  }
  if !valid_user_metadata(values) {
    None
  } else {
    Some(if fields.is_empty() { "" } else { Json::object(fields).stringify() })
  }
}

///|
fn user_metadata_record(text : String) -> String {
  if text.is_empty() {
    ""
  } else {
    "user-metadata=" + text + "\n"
  }
}

///|
fn user_metadata_operation(
  request : @http.Request,
  path : String,
  params : Array[@core.QueryParam],
) -> Bool {
  let (_, key) = @core.split_bucket_key(path)
  key is Some(_) &&
  (
    (request.meth is Put && !is_multipart_request(params)) ||
    (
      request.meth is Post &&
      @core.query_value(params, "uploads") is Some(_) &&
      @core.query_value(params, "uploadId") is None
    )
  )
}

///|
async fn stored_user_metadata(path : String) -> String {
  if !@fs.exists(path) {
    return ""
  }
  if @fs.file_size(path) > 65536L {
    raise Failure("Metadata record is too large")
  }
  let text = @utf8.decode(@fs.read_file(path).binary().clamped_view())
  let mut found = false
  let mut result = ""
  for line in text.split("\n") {
    if line.strip_prefix("user-metadata=") is Some(value) {
      if found || value.is_empty() {
        raise Failure("Duplicate user metadata record")
      }
      found = true
      result = value.to_owned()
    }
  }
  ignore(user_metadata_values(result))
  result
}
