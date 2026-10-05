package com.stockmonitor;

import com.stockmonitor.config.AppConfig;
import com.stockmonitor.config.ConfigManager;
import com.stockmonitor.http.BrowserHeaders;
import com.stockmonitor.http.HttpClientFactory;
import com.stockmonitor.http.ProxyManager;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;
import com.stockmonitor.monitor.AppleStoreClient;
import com.stockmonitor.monitor.StockMonitor;
import com.stockmonitor.notify.NotificationManager;
import com.stockmonitor.notify.PurchaseAssistant;
import com.stockmonitor.notify.WebhookNotifier;
import com.stockmonitor.util.HistoryStore;
import com.stockmonitor.util.Stats;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

/**
 * 用法：
 * <pre>
 *   java -jar iphone-stock-monitor.jar [配置文件] [--model=iphone-duo] [--once] [--test-notify] [--test-open]
 * </pre>
 * --once        只检查一轮并打印结果后退出（验证部件号/网络是否正常）
 * --test-notify 向所有已启用的提醒渠道发送一条测试消息后退出
 * --test-open   测试「有货时自动打开购买页」后退出
 */
public final class StockMonitorApplication {
    private static final Logger log = LoggerFactory.getLogger(StockMonitorApplication.class);
    private static final String VERSION = "2.0.0";

    public static void main(String[] args) throws Exception {
        Path configPath = Path.of("application.yml");
        String modelArg = null;
        boolean once = false;
        boolean testNotify = false;
        boolean testOpen = false;
        for (String a : args) {
            if (a.equals("--once")) {
                once = true;
            } else if (a.equals("--test-notify")) {
                testNotify = true;
            } else if (a.equals("--test-open")) {
                testOpen = true;
            } else if (a.startsWith("--model=")) {
                modelArg = a.substring("--model=".length());
            } else if (a.equals("-h") || a.equals("--help")) {
                System.out.println("用法: java -jar iphone-stock-monitor.jar [application.yml] [--model=KEY] [--once] [--test-notify] [--test-open]");
                return;
            } else {
                configPath = Path.of(a);
            }
        }
        if (Files.notExists(configPath)) {
            System.err.println("找不到配置文件 " + configPath.toAbsolutePath()
                    + "\n请先执行：cp application-example.yml application.yml 并按需修改");
            System.exit(1);
        }

        ConfigManager configs = new ConfigManager(configPath);
        configs.selectModel(chooseModel(configs.get(), modelArg));
        AppConfig cfg = configs.get();

        Stats stats = new Stats();
        ProxyManager proxies = new ProxyManager(cfg.proxy);
        HttpClientFactory http = new HttpClientFactory(cfg.http, proxies);
        BrowserHeaders headers = new BrowserHeaders(cfg.http.userAgents, cfg.http.extraHeaders);
        AppleStoreClient client = new AppleStoreClient(configs, http, headers);
        NotificationManager notifications = new NotificationManager(cfg.notify, stats);
        PurchaseAssistant purchase = new PurchaseAssistant(cfg.purchase);

        printBanner(configs, client, notifications, cfg);

        Sku demoSku = configs.enabledSkus().isEmpty() ? new Sku("TEST", "测试 SKU") : configs.enabledSkus().get(0);
        AvailabilityEvent demo = new AvailabilityEvent(
                CheckResult.of(demoSku, StockState.AVAILABLE, "テスト", List.of()),
                client.buyUrl(demoSku), LocalDateTime.now(), true);

        if (testNotify || testOpen) {
            if (testNotify) {
                notifications.sendTest(demo);
            }
            if (testOpen) {
                purchase.open(demo);
            }
            notifications.shutdown();
            http.shutdown();
            return;
        }
        if (cfg.notify.webhook.enabled && cfg.notify.webhook.testOnStartup) {
            notifications.sendTest(demo, WebhookNotifier.class);
        }

        ScheduledExecutorService scheduler = Executors.newScheduledThreadPool(2, r -> {
            Thread t = new Thread(r, "scheduler");
            t.setDaemon(true);
            return t;
        });
        HistoryStore history = new HistoryStore(Path.of("data", "availability-history.csv"));
        StockMonitor monitor = new StockMonitor(configs, client, notifications, purchase, history, stats, scheduler);

        if (once) {
            for (CheckResult r : monitor.checkAll(configs.enabledSkus())) {
                String state = r.isSuccess() ? r.state().label() : "失败: " + r.error();
                System.out.printf("%-36s %-10s %s %s (%dms)%n", r.sku().displayName(), state,
                        r.detail() == null ? "" : r.detail(),
                        r.pickupStores().isEmpty() ? "" : "取货: " + String.join(", ", r.pickupStores()),
                        r.latencyMs());
            }
            monitor.stop();
            scheduler.shutdownNow();
            notifications.shutdown();
            http.shutdown();
            return;
        }

        CountDownLatch done = new CountDownLatch(1);
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            log.info("正在退出……");
            monitor.stop();
            scheduler.shutdownNow();
            notifications.shutdown();
            http.shutdown();
            log.info("本次运行统计：{}", stats.summary());
            done.countDown();
        }, "shutdown"));

        configs.startWatching(scheduler);
        monitor.start();
        done.await();
    }

    private static String chooseModel(AppConfig cfg, String fromArg) throws Exception {
        Map<String, AppConfig.ModelPreset> models = cfg.monitor.models;
        if (fromArg != null && !fromArg.isBlank()) {
            return fromArg;
        }
        if (cfg.monitor.activeModel != null && !cfg.monitor.activeModel.isBlank()) {
            return cfg.monitor.activeModel;
        }
        List<String> keys = new ArrayList<>(models.keySet());
        if (keys.size() == 1 || System.console() == null) {
            return keys.get(0);
        }
        System.out.println("请选择要监控的型号：");
        for (int i = 0; i < keys.size(); i++) {
            System.out.printf("  %d) %s [%s]%n", i + 1, models.get(keys.get(i)).name, keys.get(i));
        }
        System.out.print("输入序号（回车默认 1）：");
        BufferedReader in = new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        String line = in.readLine();
        try {
            int idx = (line == null || line.isBlank()) ? 1 : Integer.parseInt(line.trim());
            return keys.get(Math.max(1, Math.min(keys.size(), idx)) - 1);
        } catch (NumberFormatException e) {
            return keys.get(0);
        }
    }

    private static void printBanner(ConfigManager configs, AppleStoreClient client,
                                    NotificationManager notifications, AppConfig cfg) {
        String line = "=".repeat(62);
        StringBuilder sb = new StringBuilder("\n").append(line).append('\n');
        sb.append("   iPhone 库存监控 + 辅助抢购（日本 Apple Store）  v").append(VERSION).append('\n');
        sb.append("-".repeat(62)).append('\n');
        sb.append("   监控型号 : ").append(configs.activeModel().name).append('\n');
        sb.append("   监控站点 : ").append(cfg.monitor.baseUrl).append('\n');
        sb.append("   检查模式 : ").append(cfg.monitor.checkMode).append('\n');
        sb.append("   购买页   : ").append(client.productPageUrl()).append('\n');
        sb.append(String.format("   检查间隔 : %.0f±%.0f 秒（下限 %.0f 秒）%n",
                cfg.monitor.interval.baseSeconds, cfg.monitor.interval.jitterSeconds, cfg.monitor.interval.minSeconds));
        sb.append("   提醒渠道 : ").append(String.join(" / ", notifications.channelNames())).append('\n');
        sb.append("   有货动作 : ").append(cfg.purchase.autoOpenBrowser ? "自动打开购买页（请提前在浏览器登录 Apple ID）" : "仅提醒").append('\n');
        sb.append("   监控 SKU : ").append(configs.enabledSkus().size()).append(" 个\n");
        for (Sku s : configs.enabledSkus()) {
            sb.append("     - ").append(s.displayName()).append('\n');
        }
        sb.append(line);
        log.info(sb.toString());
    }
}
