package com.stockmonitor.util;

import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.atomic.AtomicLong;

/** 运行统计（线程安全）。 */
public class Stats {
    private final Instant startedAt = Instant.now();
    private final AtomicLong checks = new AtomicLong();
    private final AtomicLong success = new AtomicLong();
    private final AtomicLong failures = new AtomicLong();
    private final AtomicLong totalLatency = new AtomicLong();
    private final AtomicLong hits = new AtomicLong();
    private final AtomicLong notifications = new AtomicLong();
    private final AtomicLong browserOpens = new AtomicLong();

    public void recordCheck(boolean ok, long latencyMs) {
        checks.incrementAndGet();
        (ok ? success : failures).incrementAndGet();
        totalLatency.addAndGet(latencyMs);
    }

    public void recordHit() {
        hits.incrementAndGet();
    }

    public void recordNotification() {
        notifications.incrementAndGet();
    }

    public void recordBrowserOpen() {
        browserOpens.incrementAndGet();
    }

    public String summary() {
        long c = checks.get();
        double rate = c == 0 ? 0 : success.get() * 100.0 / c;
        long avg = c == 0 ? 0 : totalLatency.get() / c;
        Duration up = Duration.between(startedAt, Instant.now());
        return String.format("运行 %dh%02dm%02ds | 检查 %d 次 | 成功率 %.1f%% | 平均响应 %dms | 有货检出 %d | 提醒 %d | 打开购买页 %d",
                up.toHours(), up.toMinutesPart(), up.toSecondsPart(), c, rate, avg,
                hits.get(), notifications.get(), browserOpens.get());
    }
}
