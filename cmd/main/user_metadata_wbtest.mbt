///|
test "user metadata preserves quoted strings and enforces its byte boundary" {
  let values : Map[String, String] = Map::from_array([
    ("owner", "a=\"b\\c"),
    ("empty", ""),
  ])
  assert_true(valid_user_metadata(values))
  assert_eq(
    user_metadata_values("{\"owner\":\"a=\\\"b\\\\c\",\"empty\":\"\"}"),
    values,
  )
  assert_true(valid_user_metadata(Map::from_array([("a", "x".repeat(2047))])))
  assert_true(!valid_user_metadata(Map::from_array([("a", "x".repeat(2048))])))
  for
    (name, value) in [
      ("", "x"),
      ("UPPER", "x"),
      ("a b", "x"),
      ("a", "line\nbreak"),
      ("a", "头像"),
    ] {
    assert_true(!valid_user_metadata(Map::from_array([(name, value)])))
  }
}
