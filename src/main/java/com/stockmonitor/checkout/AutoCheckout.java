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
        Path exe = findBrowser();
        if (exe != null) {
            // 用没有任何自动化控制的普通浏览器窗口登录（Apple 登录框在被控制的窗口里可能一直转圈），
            // 登录状态保存在同一个 profile 目录里，之后自动结账会读取它。
            try {
                Path profile = Paths.get(cfg.profileDir).toAbsolutePath();
                Files.createDirectories(profile);
                Process p = new ProcessBuilder(exe.toString(), "--user-data-dir=" + profile,
                        "--no-first-run", "--no-default-browser-check", url).inheritIO().start();
                log.info("已用普通浏览器窗口打开：{}。请登录 Apple ID，确认配送地址与支付方式，完成后【关闭这个浏览器窗口】。", exe.getFileName());
                p.waitFor();
                log.info("登录窗口已关闭，会话已保存到 {}", profile);
                return;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                return;
            } catch (Exception e) {
                log.warn("无法启动普通浏览器窗口（{}），改用自动化浏览器登录", e.getMessage());
            }
        }
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
            List<AppConfig.Step> plan = plan();
            try {
                for (AppConfig.Step step : plan) {
                    n++;
                    if (step.submit && !cfg.autoSubmit) {
                        log.warn("已执行到最后一步（第 {} 步 {}），但 auto-submit=false，停在下单前。请在浏览器中手动确认下单！",
                                n, describe(step, sku, event));
                        holdOpen(page);
                        return Outcome.STOPPED_BEFORE_SUBMIT;
                    }
                    try {
                        execute(page, step, sku, event);
                        log.info("结账步骤 {}/{} 完成：{}", n, plan.size(), describe(step, sku, event));
                    } catch (RuntimeException e) {
                        if (step.optional) {
                            log.info("结账步骤 {}/{} 可选步骤跳过：{}", n, plan.size(), describe(step, sku, event));
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
                dumpPage(page, sku);
                holdOpen(page);
                return Outcome.FAILED;
            }
        } catch (Exception e) {
            log.warn("无法启动自动结账浏览器：{}", firstLine(e));
            return Outcome.LAUNCH_FAILED;
        }
    }

    /** 找到本机已安装的浏览器（executable-path 优先，其次按 channel 在常见安装位置查找）。 */
    Path findBrowser() {
        if (cfg.executablePath != null && !cfg.executablePath.isBlank()) {
            Path p = Paths.get(cfg.executablePath);
            return Files.isRegularFile(p) ? p : null;
        }
        List<String> candidates = switch (cfg.channel == null ? "" : cfg.channel) {
            case "msedge" -> List.of(
                    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
                    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    "/usr/bin/microsoft-edge");
            case "chrome" -> List.of(
                    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
                    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
                    System.getenv("LOCALAPPDATA") + "\\Google\\Chrome\\Application\\chrome.exe",
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                    "/usr/bin/google-chrome");
            default -> List.of();
        };
        for (String c : candidates) {
            Path p = Paths.get(c);
            if (Files.isRegularFile(p)) {
                return p;
            }
        }
        return null;
    }

    /** unit-steps 重复 quantity 遍，再接上只执行一次的 steps。 */
    List<AppConfig.Step> plan() {
        List<AppConfig.Step> all = new java.util.ArrayList<>();
        int units = Math.max(1, cfg.quantity);
        for (int i = 0; i < units; i++) {
            all.addAll(cfg.unitSteps);
        }
        all.addAll(cfg.steps);
        return all;
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
            case "select" -> locator(page, step, sku, event)
                    .selectOption(expand(step.value, sku, event, false), new Locator.SelectOptionOptions().setTimeout(timeout));
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
            out = out.replace(e[0], asRegex ? jsQuote(v) : v);
        }
        return out;
    }

    /**
     * 转义正则元字符。Playwright 把 java.util.regex.Pattern 交给浏览器端的 JavaScript 正则执行，
     * 不支持 Java 的 \Q..\E，所以不能用 Pattern.quote。
     */
    static String jsQuote(String s) {
        return s.replaceAll("[.*+?^${}()|\\[\\]\\\\/]", "\\\\$0");
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

    /** 失败时把当前网址、页面上所有可点击元素的文字写进日志，并保存页面源码，方便对照真实按钮文字调整 steps。 */
    private void dumpPage(Page page, Sku sku) {
        try {
            log.info("失败时的网址：{}", page.url());
            List<String> texts = page.locator(CLICKABLE).allInnerTexts().stream()
                    .map(t -> t.replaceAll("\\s+", " ").trim())
                    .filter(t -> !t.isEmpty() && t.length() <= 60)
                    .distinct().limit(80).toList();
            log.info("页面上可点击的文字（共 {} 个）：{}", texts.size(), texts);
            Path dir = Paths.get(cfg.screenshotDir);
            Files.createDirectories(dir);
            Path file = dir.resolve(sku.partNumber.replace('/', '_') + "-" + System.currentTimeMillis() + ".html");
            Files.writeString(file, page.content());
            log.info("页面源码已保存：{}", file);
        } catch (Exception e) {
            log.debug("保存页面信息失败：{}", e.getMessage());
        }
    }

    /** SKU 里缺少的、步骤用到的占位符字段（如 color / capacity），开始前提醒用户填写。 */
    public List<String> missingFields(Sku sku) {
        List<String> missing = new java.util.ArrayList<>();
        List<AppConfig.Step> all = new java.util.ArrayList<>(cfg.unitSteps);
        all.addAll(cfg.steps);
        String used = all.stream().filter(s -> !s.optional)
                .map(s -> String.valueOf(s.text) + " " + s.selector + " " + s.value)
                .reduce("", (a, b) -> a + " " + b);
        if (used.contains("{color}") && (sku.color == null || sku.color.isBlank())) {
            missing.add("颜色");
        }
        if (used.contains("{capacity}") && (sku.capacity == null || sku.capacity.isBlank())) {
            missing.add("容量");
        }
        return missing;
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
