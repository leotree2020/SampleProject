package com.stockmonitor.util;

import com.stockmonitor.config.AppConfig;

import java.util.concurrent.ThreadLocalRandom;

public final class Jitter {
    private Jitter() {
    }

    /** base ± jitter 秒的随机间隔（毫秒），且不低于 min。 */
    public static long nextDelayMs(AppConfig.Interval cfg) {
        double j = Math.max(0, cfg.jitterSeconds);
        double offset = j == 0 ? 0 : ThreadLocalRandom.current().nextDouble(-j, j);
        double seconds = Math.max(cfg.minSeconds, cfg.baseSeconds + offset);
        return (long) (seconds * 1000);
    }
}
