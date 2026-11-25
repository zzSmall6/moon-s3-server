///|
test "bucket grants match exactly and read-write includes reads" {
  let grants : Map[String, Bool] = Map::from_array([
    ("images", false),
    ("backups", true),
  ])
  assert_true(bucket_permission(grants, "images", write=false))
  assert_true(!bucket_permission(grants, "images", write=true))
  assert_true(bucket_permission(grants, "backups", write=false))
  assert_true(bucket_permission(grants, "backups", write=true))
  assert_true(!bucket_permission(grants, "images-extra", write=false))
  assert_true(!bucket_permission(grants, "IMAGES", write=false))
  assert_true(!bucket_permission(grants, "missing", write=true))
}
