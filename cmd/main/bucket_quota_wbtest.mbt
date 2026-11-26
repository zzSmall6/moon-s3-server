///|
test "quota allows boundaries and reductions when an administrator lowers the limit" {
  assert_true(quota_allows(5L, 10L, 10L))
  assert_true(!quota_allows(5L, 11L, 10L))
  assert_true(quota_allows(20L, 19L, 10L))
  assert_true(!quota_allows(20L, 20L, 10L))
  assert_true(!quota_allows(20L, -1L, 10L))
  assert_true(quota_allows(0L, 0L, 0L))
}
