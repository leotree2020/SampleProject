package com.stockmonitor.notify;

import com.stockmonitor.checkout.AutoCheckout;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.Desktop;
import java.awt.GraphicsEnvironment;
import java.net.URI;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 辅助抢购：检测到有货时，立刻用默认浏览器打开购买页。
 * 浏览器里使用的是你自己已登录的 Apple ID 会话，「加入购物袋 → 结账 → 支付」由你本人完成。
 * 建议提前在浏览器登录 Apple ID 并保存好配送地址与支付方式，这样到货后只需几次点击。
 */
public class PurchaseAssistant {
    private static final Logger log = LoggerFactory.getLogger(PurchaseAssistant.class);

    private final AppConfig.Purchase cfg;
    private final AutoCheckout checkout;
    /** 同一时间只允许一个结账流程，避免多个 SKU 同时到货时抢同一个浏览器配置文件。 */
    private final AtomicBoolean checkoutRunning = new AtomicBoolean();

    public PurchaseAssistant(AppConfig.Purchase cfg) {
        this.cfg = cfg;
        this.checkout = new AutoCheckout(cfg.checkout);
    }

    public AutoCheckout checkout() {
        return checkout;
    }

    public boolean enabled() {
        return cfg.autoOpenBrowser || cfg.checkout.enabled;
    }

    public boolean open(AvailabilityEvent e) {
        if (cfg.checkout.enabled && !e.test()) {
            return startCheckout(e);
        }
        return openSystemBrowser(e);
    }

    private boolean startCheckout(AvailabilityEvent e) {
        if (!checkoutRunning.compareAndSet(false, true)) {
            log.info("已有自动结账流程在进行中，跳过 {}", e.sku().displayName());
            return false;
        }
        log.info("开始自动结账：{}（auto-submit={}）", e.sku().displayName(), cfg.checkout.autoSubmit);
        Thread t = new Thread(() -> {
            try {
                AutoCheckout.Outcome outcome = checkout.run(e);
                if (outcome == AutoCheckout.Outcome.LAUNCH_FAILED) {
                    openSystemBrowser(e); // 自动浏览器起不来时，至少用默认浏览器打开购买页
                }
            } finally {
                checkoutRunning.set(false);
            }
        }, "auto-checkout");
        t.start();
        return true;
    }

    private boolean openSystemBrowser(AvailabilityEvent e) {
        String url = e.buyUrl();
        try {
            if (!GraphicsEnvironment.isHeadless() && Desktop.isDesktopSupported()
                    && Desktop.getDesktop().isSupported(Desktop.Action.BROWSE)) {
                Desktop.getDesktop().browse(URI.create(url));
            } else {
                String os = System.getProperty("os.name", "").toLowerCase(Locale.ROOT);
                ProcessBuilder pb;
                if (os.contains("win")) {
                    pb = new ProcessBuilder("rundll32", "url.dll,FileProtocolHandler", url);
                } else if (os.contains("mac")) {
                    pb = new ProcessBuilder("open", url);
                } else {
                    pb = new ProcessBuilder("xdg-open", url);
                }
                pb.redirectErrorStream(true).start();
            }
            log.info("已在浏览器打开购买页：{} —— 请立即完成加购与结账！", url);
            return true;
        } catch (Exception ex) {
            log.warn("无法自动打开浏览器（{}），请手动访问：{}", ex.getMessage(), url);
            return false;
        }
    }
}
