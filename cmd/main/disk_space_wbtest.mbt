///|
test "disk reserve boundaries and outstanding writes" {
  assert_true(disk_space_allows(100L, 10L, 60L, 30L))
  assert_true(!disk_space_allows(100L, 11L, 60L, 30L))
  assert_true(!disk_space_allows(-1L, 0L, 0L, 0L))
  assert_true(!disk_space_allows(59L, 0L, 60L, 0L))
  assert_true(disk_space_allows(0L, 0L, 0L, 0L))
  assert_true(
    !disk_space_allows(9223372036854775807L, 1L, 9223372036854775807L, 1L),
  )
}
