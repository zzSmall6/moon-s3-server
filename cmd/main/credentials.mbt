///|
struct Credential {
  secret : String
  permissions : Map[String, Bool]?
}

///|
fn parse_credentials(document : Json) -> Map[String, Credential] raise {
  let entries = match document {
    Array(entries) if entries.length() >= 1 && entries.length() <= 64 => entries
    _ => raise Failure("Expected 1-64 credentials")
  }
  let seen : Map[String, Bool] = Map([])
  let active : Map[String, Credential] = Map([])
  for entry in entries {
    let fields = match entry {
      Object(fields) => fields
      _ => raise Failure("Expected credential object")
    }
    if fields
      .keys()
      .any(name => {
        !["access_key", "secret_key", "enabled", "permissions"].contains(name)
      }) {
      raise Failure("Unknown credential field")
    }
    let access = match fields.get("access_key") {
      Some(String(value)) => value
      _ => raise Failure("Expected access key")
    }
    let secret = match fields.get("secret_key") {
      Some(String(value)) => value
      _ => raise Failure("Expected secret key")
    }
    if access.is_empty() ||
      access.length() > 128 ||
      !access
      .to_array()
      .all(character => {
        (character >= 'a' && character <= 'z') ||
        (character >= 'A' && character <= 'Z') ||
        (character >= '0' && character <= '9') ||
        character == '-' ||
        character == '_'
      }) ||
      secret.trim().is_empty() ||
      @utf8.encode(secret).length() > 4096 ||
      secret
      .to_array()
      .any(character => character.to_int() < 32 || character.to_int() == 127) ||
      seen.contains(access) {
      raise Failure("Invalid or duplicate credential")
    }
    seen[access] = true
    let enabled = match fields.get("enabled") {
      None => true
      Some(True) => true
      Some(False) => false
      _ => raise Failure("Expected boolean enabled")
    }
    let permissions = match fields.get("permissions") {
      None => None
      Some(Object(grants)) => {
        if grants.length() > 64 {
          raise Failure("Too many bucket grants")
        }
        let permissions : Map[String, Bool] = Map([])
        for bucket, permission in grants {
          if !@core.valid_bucket_name(bucket) ||
            bucket == "metrics" ||
            bucket == "healthz" {
            raise Failure("Invalid bucket grant")
          }
          permissions[bucket] = match permission {
            String("read") => false
            String("read-write") => true
            _ => raise Failure("Invalid bucket permission")
          }
        }
        Some(permissions)
      }
      _ => raise Failure("Expected bucket permission object")
    }
    if enabled {
      active[access] = { secret, permissions, }
    }
  }
  active
}

///|
fn load_credentials(
  text : String?,
  access : String?,
  secret : String?,
) -> Map[String, Credential]? raise {
  match text {
    Some(text) => {
      if access is Some(_) ||
        secret is Some(_) ||
        @utf8.encode(text).length() > 65536 {
        raise Failure("Conflicting or oversized credentials")
      }
      Some(
        parse_credentials(
          @json.parse(text, max_nesting_depth=4, reject_duplicate_keys=true),
        ),
      )
    }
    None => {
      if !valid_credentials(access, secret) {
        raise Failure("Incomplete legacy credentials")
      }
      match (access, secret) {
        (Some(access), Some(secret)) =>
          Some(
            Map::from_array([
              (access, Credential::{ secret, permissions: None, }),
            ]),
          )
        _ => None
      }
    }
  }
}
