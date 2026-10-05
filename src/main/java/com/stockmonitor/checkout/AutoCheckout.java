package com.stockmonitor.checkout;

import com.microsoft.playwright.BrowserContext;
import com.microsoft.playwright.BrowserType;
import com.microsoft.playwright.Locator;
import com.microsoft.playwright.Page;
import com.microsoft.playwright.Playwright;
import com.microsoft.playwright.options.LoadState;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.model.Sku;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.regex.Pattern;

/**
 * 到货后在你自己的浏览器配置文件里依次执行 checkout.steps。
 * 全程使用你已登录的会话；遇到密码 / 验证码 / 3D Secure 等需要人工的环节，窗口会保持打开等你接手。
 */
public class AutoCheckout {
    private static final Logger log = LoggerFactory.getLogger(AutoCheckout.class);
    private static final String CLICKABLE = "button, a, [role=button], [role=radio], [role=option], label, input[type=submit]";

    public enum Outcome { SUBMITTED, STOPPED_BEFORE_SUBMIT, FAILED, LAUNCH_FAILED }

    private final AppConfig.Checkout cfg;

    public AutoCheckout(AppConfig.Checkout cfg) {
        this.cfg = cfg;
    }

    /** 打开浏览器让你手动登录 Apple ID、确认地址与支付方式，关闭窗口即保存会话。 */
    public void interactiveLogin(String url) {
        try (Playwright pw = Playwright.create()) {
            BrowserContext ctx = launch(pw, false);
            Page page = ctx.pages().isEmpty() ? ctx.newPage() : ctx.pages().get(0);
            page.navigate(url);
            log.info("请在打开的浏览器中登录 Apple ID，并确认配送地址与支付方式。完成后关闭浏览器窗口即可。");
            page.waitForClose(new Page.WaitForCloseOptions().setTimeout(0), () -> { });
        } catch (Exception e) {
            log.warn("登录窗口异常结束：{}", e.getMessage());
        }
    }

    public Outcome run(AvailabilityEvent event) {
        Sku sku = event.sku();
        try (Playwright pw = Playwright.create()) {
            BrowserContext ctx = launch(pw, cfg.headless);
            Page page = ctx.pages().isEmpty() ? ctx.newPage() : ctx.pages().get(0);
            page.setDefaultTimeout(cfg.defaultTimeoutMs);
            int n = 0;
            try {
                for (AppConfig.Step step : cfg.steps) {
                    n++;
                    if (step.submit && !cfg.autoSubmit) {
                        log.warn("已执行到最后一步（第 {} 步 {}），但 auto-submit=false，停在下单前。请在浏览器中手动确认下单！",
                                n, describe(step, sku, event));
                        holdOpen(page);
                        return Outcome.STOPPED_BEFORE_SUBMIT;
                    }
                    try {
                        execute(page, step, sku, event);
                        log.info("结账步骤 {}/{} 完成：{}", n, cfg.steps.size(), describe(step, sku, event));
                    } catch (RuntimeException e) {
                        if (step.optional) {
                            log.info("结账步骤 {}/{} 可选步骤跳过：{}", n, cfg.steps.size(), describe(step, sku, event));
                            continue;
                        }
                        throw e;
                    }
                }
                log.info("所有结账步骤已执行完毕。请到邮箱 / Apple 账户确认订单状态；如出现验证环节请在浏览器中完成。");
                holdOpen(page);
                return Outcome.SUBMITTED;
            } catch (RuntimeException e) {
                log.warn("自动结账在第 {} 步失败：{}（浏览器保持打开，请手动接手）", n, firstLine(e));
                screenshot(page, sku);
                holdOpen(page);
                return Outcome.FAILED;
            }
        } catch (Exception e) {
            log.warn("无法启动自动结账浏览器：{}", firstLine(e));
            return Outcome.LAUNCH_FAILED;
        }
    }

    private BrowserContext launch(Playwright pw, boolean headless) {
        BrowserType.LaunchPersistentContextOptions opts = new BrowserType.LaunchPersistentContextOptions()
                .setHeadless(headless)
                .setLocale("ja-JP")
                .setTimezoneId("Asia/Tokyo")
                .setViewportSize(1366, 900);
        if (cfg.executablePath != null && !cfg.executablePath.isBlank()) {
            opts.setExecutablePath(Paths.get(cfg.executablePath));
        } else if (cfg.channel != null && !cfg.channel.isBlank()) {
            opts.setChannel(cfg.channel);
        }
        return pw.chromium().launchPersistentContext(Paths.get(cfg.profileDir), opts);
    }

    void execute(Page page, AppConfig.Step step, Sku sku, AvailabilityEvent event) {
        double timeout = step.timeoutMs > 0 ? step.timeoutMs : cfg.defaultTimeoutMs;
        String action = step.action == null ? "click" : step.action;
        switch (action) {
            case "goto" -> {
                String url = step.value == null || step.value.isBlank() ? event.buyUrl() : expand(step.value, sku, event, false);
                page.navigate(url);
                page.waitForLoadState(LoadState.DOMCONTENTLOADED);
            }
            case "click" -> locator(page, step, sku, event).click(new Locator.ClickOptions().setTimeout(timeout));
            case "fill" -> locator(page, step, sku, event)
                    .fill(expand(step.value, sku, event, false), new Locator.FillOptions().setTimeout(timeout));
            case "press" -> locator(page, step, sku, event)
                    .press(step.value, new Locator.PressOptions().setTimeout(timeout));
            case "wait" -> page.waitForTimeout(Long.parseLong(step.value == null ? "500" : step.value));
            case "wait-url" -> page.waitForURL(Pattern.compile(expand(step.value, sku, event, true)),
                    new Page.WaitForURLOptions().setTimeout(timeout));
            default -> throw new IllegalArgumentException("未知的 action: " + action);
        }
    }

    private Locator locator(Page page, AppConfig.Step step, Sku sku, AvailabilityEvent event) {
        if (step.selector != null && !step.selector.isBlank()) {
            return page.locator(expand(step.selector, sku, event, false)).first();
        }
        Pattern text = Pattern.compile(expand(step.text, sku, event, true));
        return page.locator(CLICKABLE).filter(new Locator.FilterOptions().setHasText(text)).first();
    }

    /** 展开占位符；asRegex=true 时对替换值做 quote，避免颜色 / 容量里的特殊字符破坏正则。 */
    static String expand(String template, Sku sku, AvailabilityEvent event, boolean asRegex) {
        if (template == null) {
            return "";
        }
        String out = template;
        for (String[] e : List.of(
                new String[]{"{color}", sku.color}, new String[]{"{capacity}", sku.capacity},
                new String[]{"{partNumber}", sku.partNumber}, new String[]{"{name}", sku.name},
                new String[]{"{buyUrl}", event.buyUrl()})) {
            String v = e[1] == null ? "" : e[1];
            if (v.isBlank() && out.contains(e[0])) {
                // 空值会让正则匹配到任意按钮，必须拒绝
                throw new IllegalStateException("占位符 " + e[0] + " 为空，请在 SKU 中填写对应字段（color / capacity 等）");
            }
            out = out.replace(e[0], asRegex ? Pattern.quote(v) : v);
        }
        return out;
    }

    private String describe(AppConfig.Step s, Sku sku, AvailabilityEvent ev) {
        String target = s.selector != null && !s.selector.isBlank() ? s.selector : s.text != null ? s.text : s.value;
        String shown;
        try {
            shown = target == null ? "" : expand(target, sku, ev, false);
        } catch (IllegalStateException e) {
            shown = target + "（占位符为空）"; // 仅用于日志，不能因此中断流程
        }
        return (s.action == null ? "click" : s.action) + " " + shown;
    }

    private void screenshot(Page page, Sku sku) {
        try {
            Path dir = Paths.get(cfg.screenshotDir);
            Files.createDirectories(dir);
            Path file = dir.resolve(sku.partNumber.replace('/', '_') + "-" + System.currentTimeMillis() + ".png");
            page.screenshot(new Page.ScreenshotOptions().setPath(file));
            log.info("失败截图已保存：{}", file);
        } catch (Exception ignored) {
        }
    }

    /** 保持窗口打开，直到你关闭它（无头模式下不等待）。 */
    private void holdOpen(Page page) {
        if (cfg.headless) {
            return;
        }
        try {
            page.waitForClose(new Page.WaitForCloseOptions().setTimeout(0), () -> { });
        } catch (RuntimeException ignored) {
        }
    }

    private static String firstLine(Throwable t) {
        String m = String.valueOf(t.getMessage()).replaceAll("\\s+", " ").trim();
        return m.length() > 400 ? m.substring(0, 400) + "…" : m;
    }
}
