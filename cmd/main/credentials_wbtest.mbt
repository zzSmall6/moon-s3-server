///|
test "credential set preserves authentication with all keys disabled" {
  assert_true(load_credentials(None, None, None) is None)
  let legacy = load_credentials(None, Some("legacy"), Some("secret")).unwrap()
  assert_eq(
    legacy.get("legacy").map(credential => credential.secret),
    Some("secret"),
  )
  let disabled = load_credentials(
    Some(
      "[{\"access_key\":\"revoked\",\"secret_key\":\"secret\",\"enabled\":false}]",
    ),
    None,
    None,
  ).unwrap()
  assert_eq(disabled.length(), 0)
  let credentials = load_credentials(
    Some(
      "[{\"access_key\":\"first\",\"secret_key\":\"one\"},{\"access_key\":\"second\",\"secret_key\":\"two\",\"enabled\":true}]",
    ),
    None,
    None,
  ).unwrap()
  assert_eq(
    credentials.get("first").map(credential => credential.secret),
    Some("one"),
  )
  assert_eq(
    credentials.get("second").map(credential => credential.secret),
    Some("two"),
  )
}
