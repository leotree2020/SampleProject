package com.stockmonitor.monitor;

import com.stockmonitor.config.AppConfig;

import java.util.concurrent.ThreadLocalRandom;

/** 指数退避 + 全抖动（full jitter）。 */
public final class RetryPolicy {
    private RetryPolicy() {
    }

    /** 第 attempt 次失败（从 1 开始）后应等待的毫秒数。 */
    public static long backoffMs(AppConfig.Retry cfg, int attempt) {
        double ceiling = cfg.backoffBaseMs * Math.pow(cfg.backoffMultiplier, Math.max(0, attempt - 1));
        long cap = (long) Math.min(cfg.maxBackoffMs, ceiling);
        return cap <= 0 ? 0 : ThreadLocalRandom.current().nextLong(cap / 2, cap + 1);
    }
}
