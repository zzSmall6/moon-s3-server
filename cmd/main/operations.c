#include <stdio.h>
#include <stdint.h>
#include <limits.h>
#include <sys/statvfs.h>
#include "moonbit.h"

void moon_s3_flush_logs(void) {
  fflush(stdout);
}

int64_t moon_s3_available_disk_bytes(moonbit_bytes_t path) {
  struct statvfs status;
  if (statvfs((const char *)path, &status) != 0) {
    return -1;
  }
  uint64_t blocks = status.f_bavail;
  uint64_t unit = status.f_frsize;
  if (unit != 0 && blocks > INT64_MAX / unit) {
    return INT64_MAX;
  }
  return (int64_t)(blocks * unit);
}
