package com.stockmonitor.monitor;

import com.stockmonitor.config.AppConfig;
import com.stockmonitor.config.ConfigManager;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;
import com.stockmonitor.notify.NotificationManager;
import com.stockmonitor.notify.PurchaseAssistant;
import com.stockmonitor.util.HistoryStore;
import com.stockmonitor.util.Jitter;
import com.stockmonitor.util.Stats;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/**
 * 调度器：按「轮」检查所有启用的 SKU，一轮结束后再按随机抖动间隔安排下一轮（天然背压，不会堆积请求）。
 * 连续多轮全部失败时进入冷却。
 */
public class StockMonitor {
    private static final Logger log = LoggerFactory.getLogger(StockMonitor.class);

    private final ConfigManager configs;
    private final AppleStoreClient client;
    private final NotificationManager notifications;
    private final PurchaseAssistant purchase;
    private final HistoryStore history;
    private final Stats stats;
    private final ScheduledExecutorService scheduler;
    private final ExecutorService workers;

    private final Map<String, StockState> lastState = new ConcurrentHashMap<>();
    private final Map<String, CheckResult> lastResult = new ConcurrentHashMap<>();
    private final Map<String, Long> lastNotifyAt = new ConcurrentHashMap<>();
    private final Set<String> stopped = ConcurrentHashMap.newKeySet();
    private int consecutiveFailedRounds;
    private volatile boolean running;

    public StockMonitor(ConfigManager configs, AppleStoreClient client, NotificationManager notifications,
                        PurchaseAssistant purchase, HistoryStore history, Stats stats,
                        ScheduledExecutorService scheduler) {
        this.configs = configs;
        this.client = client;
        this.notifications = notifications;
        this.purchase = purchase;
        this.history = history;
        this.stats = stats;
        this.scheduler = scheduler;
        int threads = Math.max(1, configs.get().monitor.concurrency);
        this.workers = Executors.newFixedThreadPool(threads, r -> {
            Thread t = new Thread(r, "checker");
            t.setDaemon(true);
            return t;
        });
    }

    public void start() {
        running = true;
        scheduler.execute(this::loop);
        scheduler.scheduleWithFixedDelay(this::printStatus, 30, 30, TimeUnit.SECONDS);
    }

    public void stop() {
        running = false;
        workers.shutdownNow();
    }

    private void loop() {
        if (!running) {
            return;
        }
        long delay;
        try {
            delay = runRound();
        } catch (Throwable t) {
            log.error("本轮检查异常：{}", t.toString(), t);
            delay = Jitter.nextDelayMs(configs.get().monitor.interval);
        }
        if (running) {
            scheduler.schedule(this::loop, delay, TimeUnit.MILLISECONDS);
        }
    }

    /** 执行一轮检查，返回距下一轮的等待毫秒数。 */
    long runRound() throws InterruptedException {
        AppConfig cfg = configs.get();
        List<Sku> skus = configs.enabledSkus().stream().filter(s -> !stopped.contains(s.partNumber)).toList();
        if (skus.isEmpty()) {
            log.warn("当前没有需要监控的 SKU（检查 application.yml 中 enabled / part-number）");
            return 10_000;
        }
        List<CheckResult> results = checkAll(skus);
        int failed = 0;
        int tabsOpened = 0;
        for (CheckResult r : results) {
            stats.recordCheck(r.isSuccess(), r.latencyMs());
            if (!r.isSuccess()) {
                failed++;
                log.warn("{} 查询失败：{}", r.sku().displayName(), r.error());
                lastResult.put(r.sku().partNumber, r);
                continue;
            }
            tabsOpened += handle(r, cfg, tabsOpened);
        }

        if (failed == results.size()) {
            consecutiveFailedRounds++;
            if (consecutiveFailedRounds >= cfg.monitor.cooldown.errorThreshold) {
                consecutiveFailedRounds = 0;
                long cool = cfg.monitor.cooldown.afterConsecutiveErrorsMs;
                log.warn("连续 {} 轮全部失败，进入冷却 {} 秒（若持续 403/429/541，请调大间隔或更换网络）",
                        cfg.monitor.cooldown.errorThreshold, cool / 1000);
                return cool;
            }
        } else {
            consecutiveFailedRounds = 0;
        }
        return Jitter.nextDelayMs(cfg.monitor.interval);
    }

    public List<CheckResult> checkAll(List<Sku> skus) throws InterruptedException {
        List<Future<CheckResult>> futures = new ArrayList<>();
        for (Sku s : skus) {
            futures.add(workers.submit(() -> client.check(s)));
        }
        List<CheckResult> results = new ArrayList<>();
        for (int i = 0; i < futures.size(); i++) {
            try {
                results.add(futures.get(i).get(5, TimeUnit.MINUTES));
            } catch (ExecutionException | TimeoutException e) {
                futures.get(i).cancel(true);
                results.add(CheckResult.failed(skus.get(i), e.toString(), 0));
            }
        }
        return results;
    }

    /** 处理一条成功结果，返回本次打开的浏览器标签数（0 或 1）。 */
    private int handle(CheckResult r, AppConfig cfg, int tabsOpenedThisRound) {
        String pn = r.sku().partNumber;
        StockState prev = lastState.put(pn, r.state());
        lastResult.put(pn, r);

        if (prev != r.state()) {
            log.info("{} 状态变化：{} → {}（{}，{}ms）", r.sku().displayName(),
                    prev == null ? "初始" : prev.label(), r.state().label(), r.detail(), r.latencyMs());
        } else {
            log.debug("{}：{}（{}ms）", r.sku().displayName(), r.state().label(), r.latencyMs());
        }
        if (!r.isAvailable()) {
            return 0;
        }

        boolean restock = prev != StockState.AVAILABLE;
        long now = System.currentTimeMillis();
        long renotifyMs = cfg.monitor.renotifySeconds * 1000;
        boolean renotify = renotifyMs > 0 && now - lastNotifyAt.getOrDefault(pn, 0L) >= renotifyMs;
        if (!restock && !renotify) {
            return 0;
        }

        AvailabilityEvent event = new AvailabilityEvent(r, client.buyUrl(r.sku()), LocalDateTime.now(), false);
        if (restock) {
            stats.recordHit();
            history.append(r);
        }
        lastNotifyAt.put(pn, now);
        notifications.dispatch(event);

        int opened = 0;
        boolean shouldOpen = restock || !cfg.purchase.openOncePerRestock;
        if (purchase.enabled() && shouldOpen && tabsOpenedThisRound < cfg.purchase.maxTabsPerRound) {
            if (purchase.open(event)) {
                stats.recordBrowserOpen();
                opened = 1;
            }
        }
        if (cfg.purchase.stopSkuAfterHit) {
            stopped.add(pn);
            log.info("{} 已命中，按配置停止监控该 SKU", r.sku().displayName());
        }
        return opened;
    }

    public void printStatus() {
        try {
            StringBuilder sb = new StringBuilder("\n------------------------ 状态面板 ------------------------\n");
            sb.append(stats.summary()).append('\n');
            for (Sku s : configs.enabledSkus()) {
                CheckResult r = lastResult.get(s.partNumber);
                String state = r == null ? "等待首次检查" : !r.isSuccess() ? "查询失败" : r.state().label();
                if (stopped.contains(s.partNumber)) {
                    state += "（已停止）";
                }
                sb.append(String.format("  %-34s %s%n", s.displayName(), state));
            }
            sb.append("----------------------------------------------------------");
            log.info(sb.toString());
        } catch (Exception e) {
            log.debug("打印状态失败", e);
        }
    }
}
