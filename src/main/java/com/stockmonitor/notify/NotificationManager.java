package com.stockmonitor.notify;

import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.util.Stats;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

/** 按配置装配提醒渠道，并异步分发（单个渠道失败不影响其它渠道与监控主循环）。 */
public class NotificationManager {
    private static final Logger log = LoggerFactory.getLogger(NotificationManager.class);

    private final List<Notifier> notifiers = new ArrayList<>();
    private final ExecutorService executor = Executors.newFixedThreadPool(4, r -> {
        Thread t = new Thread(r, "notify");
        t.setDaemon(true);
        return t;
    });
    private final Stats stats;

    public NotificationManager(AppConfig.Notify cfg, Stats stats) {
        this.stats = stats;
        if (cfg.console) {
            notifiers.add(new ConsoleNotifier());
        }
        if (cfg.desktop) {
            if (DesktopNotifier.supported()) {
                notifiers.add(new DesktopNotifier());
            } else {
                log.info("当前环境不支持系统托盘，桌面通知已自动禁用");
            }
        }
        if (cfg.sound) {
            notifiers.add(new SoundNotifier(cfg.soundFile));
        }
        if (cfg.email.enabled) {
            if (cfg.email.username.isBlank() || cfg.email.to.isEmpty()) {
                log.warn("邮件提醒已启用但 username / to 未配置，已跳过");
            } else {
                notifiers.add(new EmailNotifier(cfg.email));
            }
        }
        if (cfg.webhook.enabled) {
            WebhookNotifier w = new WebhookNotifier(cfg.webhook);
            if (w.hasTargets()) {
                notifiers.add(w);
            } else {
                log.warn("Webhook 已启用但未填写任何地址，已跳过");
            }
        }
    }

    public List<String> channelNames() {
        return notifiers.stream().map(Notifier::name).toList();
    }

    public void dispatch(AvailabilityEvent event) {
        stats.recordNotification();
        for (Notifier n : notifiers) {
            executor.submit(() -> {
                try {
                    n.notify(event);
                } catch (Exception e) {
                    log.warn("[{}] 提醒发送失败：{}", n.name(), e.getMessage());
                }
            });
        }
    }

    /** 同步发送测试消息并返回每个渠道的结果，用于 --test-notify。 */
    public void sendTest(AvailabilityEvent event, Class<?>... only) {
        for (Notifier n : notifiers) {
            if (only.length > 0 && List.of(only).stream().noneMatch(c -> c.isInstance(n))) {
                continue;
            }
            try {
                n.notify(event);
                log.info("[{}] 测试提醒发送成功", n.name());
            } catch (Exception e) {
                log.warn("[{}] 测试提醒发送失败：{}", n.name(), e.getMessage());
            }
        }
    }

    public void shutdown() {
        executor.shutdown();
        try {
            executor.awaitTermination(10, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
