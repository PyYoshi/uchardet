/* SPDX-License-Identifier: MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later */

/* Detector lifecycle checks that the per-file detection tests do not cover.
 * Run them under AddressSanitizer to catch use-after-free regressions. */

#include <stdio.h>
#include <string.h>

#include "../src/uchardet.h"

static int
check_weighted_reset_drops_candidates(void)
{
    static const char data[] = "plain ASCII text";
    uchardet_t handle;
    const char *encoding;
    int failed;

    handle = uchardet_new();
    uchardet_weigh_language(handle, "en", 0.5f);
    uchardet_handle_data(handle, data, sizeof(data) - 1);
    uchardet_data_end(handle);
    if (uchardet_get_n_candidates(handle) == 0)
    {
        fprintf(stderr, "weighted reset: expected a candidate before reset\n");
        uchardet_delete(handle);
        return 1;
    }

    /* Reset() frees the candidate strings, so the weighted candidates that
     * point at them must go too. */
    uchardet_reset(handle);
    uchardet_data_end(handle);
    encoding = uchardet_get_encoding(handle, 0);
    failed = uchardet_get_n_candidates(handle) != 0 || strcmp(encoding, "") != 0;
    if (failed)
        fprintf(stderr, "weighted reset: stale candidate after reset\n");

    uchardet_delete(handle);
    return failed;
}

int
main(void)
{
    return check_weighted_reset_drops_candidates();
}
