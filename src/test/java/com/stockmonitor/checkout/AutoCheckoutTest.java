package com.stockmonitor.checkout;

import com.sun.net.httpserver.HttpServer;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** 用本地模拟的「选配置 → 加入购物袋 → 结账 → 下单」页面验证点击流程；没有可用的 Chromium 时跳过。 */
class AutoCheckoutTest {
    private HttpServer server;
    private final List<String> hits = new CopyOnWriteArrayList<>();
    @TempDir
    Path tmp;

    @BeforeEach
    void startServer() throws Exception {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        page("/product", "<h1>iPhone</h1>"
                + "<label role='radio' onclick=\"fetch('/picked-color')\">ナイトスカイ</label>"
                + "<label role='radio' onclick=\"fetch('/picked-capacity')\">256GB</label>"
                + "<button onclick=\"location='/bag?added=1'\">バッグに追加</button>");
        // 复刻 Apple 日本站 iPhone 购买页的真实结构（取自一次真实运行保存的页面源码）：
        // 逐步解锁的单选框（型号→颜色→容量→下取り→支付→运营商→AppleCare），前一步没选，后面全是 disabled；
        // 型号名里是不换行空格，容量是「256」「GB」分开的两段，页面里还有同名的干扰链接。
        page("/real", """
                <h1>iPhone 18 Proを購入</h1>
                <a href="#" onclick="rec('nav-wrong');return false">iPhone 18 Pro</a>
                <div data-analytics-section="dimensionScreensize">
                  <input type="radio" name="m" id="m1" data-g="m"><label for="m1"><span>iPhone&nbsp;18&nbsp;Pro</span> 6.3インチディスプレイ 219,800円から</label>
                  <input type="radio" name="m" id="m2" data-g="m"><label for="m2"><span>iPhone&nbsp;18&nbsp;Pro&nbsp;Max</span> 6.9インチディスプレイ 239,800円から</label>
                </div>
                <div data-analytics-section="dimensionColor">
                  <input type="radio" name="c" id="c-burgundy" data-g="c" disabled><label for="c-burgundy"><span>バーガンディ</span></label>
                  <input type="radio" name="c" id="c-black" data-g="c" disabled><label for="c-black"><span>ブラック</span></label>
                </div>
                <div data-analytics-section="dimensionCapacity">
                  <input type="radio" name="cap" id="cap-256" data-g="cap" disabled><label for="cap-256"><span>256</span> <span>GB</span> <span>脚注 1</span> 219,800円から</label>
                  <input type="radio" name="cap" id="cap-512" data-g="cap" disabled><label for="cap-512"><span>512</span> <span>GB</span> <span>脚注 1</span> 254,800円から</label>
                </div>
                <div data-analytics-section="tradein">
                  <input type="radio" name="t" id="t-yes" data-g="t" disabled><label for="t-yes">下取りを追加する</label>
                  <input type="radio" name="t" id="t-no" data-g="t" disabled><label for="t-no">下取りを利用しない</label>
                </div>
                <div data-analytics-section="paymentOptions">
                  <input type="radio" name="pay" id="pay-full" data-g="pay" disabled><label for="pay-full">一括払いまたはそのほかの支払い方法 254,800円</label>
                  <input type="radio" name="pay" id="pay-finance" data-g="pay" disabled><label for="pay-finance">ペイディあと払いプランApple専用 7,077円/月の36回払い</label>
                </div>
                <div data-analytics-section="carrierModel">
                  <input type="radio" name="sim" id="sim-docomo" data-g="sim" disabled><label for="sim-docomo">ドコモ 通信キャリア割引</label>
                  <input type="radio" name="sim" id="sim-free" data-g="sim" disabled><label for="sim-free">SIMフリー あとで通信キャリアと接続する</label>
                </div>
                <div data-analytics-section="applecare">
                  <input type="radio" name="care" id="care-plan" data-g="care" disabled><label for="care-plan">AppleCare+ 盗難・紛失プラン</label>
                  <input type="radio" name="care" id="care-no" data-g="care" disabled><label for="care-no">AppleCareによる保証を追加しない</label>
                </div>
                <div data-analytics-section="summary"><button id="cont" disabled onclick="rec('add-to-bag').finally(() => { location = '/bag'; })">続ける</button></div>
                <a href="#" onclick="rec('combo-wrong');return false">256GB 脚注 1 ブラック 239,800円</a>
                <script>
                  function rec(n){return fetch('/rec?n='+n)}
                  const simFirst = new URLSearchParams(location.search).get('o') === 'simfirst';
                  const order = simFirst ? ['m','c','cap','t','sim','pay','care'] : ['m','c','cap','t','pay','sim','care'];
                  document.querySelectorAll('input[type=radio]').forEach(i => i.addEventListener('change', () => {
                    rec(i.id);
                    const next = order[order.indexOf(i.dataset.g) + 1];
                    if (next) { document.querySelectorAll('input[data-g=' + next + ']').forEach(x => x.disabled = false); }
                    else { const b = document.getElementById('cont'); b.disabled = false; b.textContent = 'バッグに追加'; }
                  }));
                </script>""");
        server.createContext("/rec", ex -> {
            hits.add(ex.getRequestURI().toString());
            ex.sendResponseHeaders(200, -1);
            ex.close();
        });
        page("/exact", "<h1>Exact</h1>"
                + "<a href='#' onclick=\"fetch('/wrong');return false\">ブラック 脚注 239,800円</a>"
                + "<label onclick=\"fetch('/right')\">ブラック</label>");
        page("/covered", "<h1>Covered</h1>"
                + "<button onclick=\"fetch('/forced')\">押せないボタン</button>"
                + "<div style='position:fixed;inset:0;background:transparent'></div>");
        for (String p : new String[]{"/right", "/wrong", "/forced"}) {
            server.createContext(p, ex -> {
                hits.add(p);
                ex.sendResponseHeaders(200, -1);
                ex.close();
            });
        }
        page("/bag", "<h1>Bag</h1>"
                + "<select name='quantity' aria-label='数量' onchange=\"fetch('/qty?v='+this.value)\">"
                + "<option value='1'>1</option><option value='2'>2</option></select>"
                + "<a href='/checkout'>ご注文手続きへ</a>");
        server.createContext("/qty", ex -> {
            hits.add(ex.getRequestURI().toString());
            ex.sendResponseHeaders(200, -1);
            ex.close();
        });
        page("/checkout", "<h1>Checkout</h1><button onclick=\"fetch('/placed');document.body.append('done')\">注文を確定</button>");
        for (String p : new String[]{"/picked-color", "/picked-capacity"}) {
            server.createContext(p, ex -> {
                hits.add(p);
                ex.sendResponseHeaders(200, -1);
                ex.close();
            });
        }
        server.createContext("/placed", ex -> {
            hits.add("placed");
            ex.sendResponseHeaders(200, -1);
            ex.close();
        });
        server.start();
    }

    @AfterEach
    void stopServer() {
        server.stop(0);
    }

    private void page(String path, String body) {
        server.createContext(path, ex -> {
            hits.add(path);
            byte[] b = ("<html><body>" + body + "</body></html>").getBytes(StandardCharsets.UTF_8);
            ex.getResponseHeaders().add("Content-Type", "text/html; charset=utf-8");
            ex.sendResponseHeaders(200, b.length);
            ex.getResponseBody().write(b);
            ex.close();
        });
    }

    private String base() {
        return "http://127.0.0.1:" + server.getAddress().getPort();
    }

    private static String chromium() {
        for (String p : new String[]{"/opt/pw-browsers/chromium/chrome-linux/chrome", "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"}) {
            if (Files.isExecutable(Path.of(p))) {
                return p;
            }
        }
        return null;
    }

    private AppConfig.Checkout cfg(boolean autoSubmit) {
        AppConfig.Checkout c = new AppConfig.Checkout();
        c.enabled = true;
        c.autoSubmit = autoSubmit;
        c.headless = true;
        c.executablePath = chromium();
        c.profileDir = tmp.resolve("profile-" + autoSubmit).toString();
        c.screenshotDir = tmp.resolve("shots").toString();
        c.defaultTimeoutMs = 3000;
        c.steps = new ArrayList<>(List.of(
                step("goto", null, null, false, false),
                step("click", "{color}", null, true, false),
                step("click", "{capacity}", null, true, false),
                step("click", "バッグに追加", null, false, false),
                step("click", "ご注文手続き", null, false, false),
                step("click", "注文を確定", null, false, true)));
        return c;
    }

    private static AppConfig.Step step(String action, String text, String value, boolean optional, boolean submit) {
        AppConfig.Step s = new AppConfig.Step();
        s.action = action;
        s.text = text;
        s.value = value;
        s.optional = optional;
        s.submit = submit;
        return s;
    }

    private AvailabilityEvent event(Sku sku) {
        return new AvailabilityEvent(CheckResult.of(sku, StockState.AVAILABLE, "", List.of()),
                base() + "/product", LocalDateTime.now(), false);
    }

    private Sku sku(String color, String capacity) {
        Sku s = new Sku("MJR54J/A", "test");
        s.color = color;
        s.capacity = capacity;
        return s;
    }

    @Test
    void stopsBeforeSubmitByDefault() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AutoCheckout.Outcome o = new AutoCheckout(cfg(false)).run(event(sku("ナイトスカイ", "256GB")));
        assertEquals(AutoCheckout.Outcome.STOPPED_BEFORE_SUBMIT, o);
        assertTrue(hits.contains("/checkout"), "应已走到结账页: " + hits);
        assertTrue(hits.contains("/picked-color") && hits.contains("/picked-capacity"), "颜色和容量应已被点中: " + hits);
        assertTrue(!hits.contains("placed"), "auto-submit=false 时不能提交订单");
    }

    @Test
    void submitsOnlyWhenEnabled() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AutoCheckout.Outcome o = new AutoCheckout(cfg(true)).run(event(sku("ナイトスカイ", "256GB")));
        assertEquals(AutoCheckout.Outcome.SUBMITTED, o);
        assertTrue(hits.contains("placed"), "auto-submit=true 时应点击最后一步: " + hits);
    }

    @Test
    void blankColorSkipsOptionalStepInsteadOfClickingAnything() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AutoCheckout.Outcome o = new AutoCheckout(cfg(false)).run(event(sku("", "")));
        assertEquals(AutoCheckout.Outcome.STOPPED_BEFORE_SUBMIT, o);
        assertTrue(!hits.contains("placed"));
    }

    @Test
    void emptyPlaceholderIsRejected() {
        AvailabilityEvent ev = event(sku("", "256GB"));
        assertThrows(IllegalStateException.class, () -> AutoCheckout.expand("{color}", ev.sku(), ev, true));
        assertEquals("256\\s*GB", AutoCheckout.expand("{capacity}", ev.sku(), ev, true));
        assertEquals("iPhone\\s+18\\s+Pro\\s+\\(256\\s*GB\\)", AutoCheckout.jsQuote("iPhone 18 Pro (256GB)"));
    }

    @Test
    void selectsQuantityTwoOnBagPage() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.steps.clear();
        c.unitSteps = new ArrayList<>(List.of(
                step("goto", null, null, false, false),
                step("click", "バッグに追加", null, false, false)));
        c.steps = new ArrayList<>(List.of(
                selectStep("select[name*='quantity' i], select[aria-label*='数量']", "2"),
                step("click", "ご注文手続き", null, false, false)));
        AutoCheckout.Outcome o = new AutoCheckout(c).run(event(sku("ナイトスカイ", "256GB")));
        assertEquals(AutoCheckout.Outcome.SUBMITTED, o);
        assertTrue(hits.contains("/qty?v=2"), "购物袋里的数量应被选为 2: " + hits);
        assertEquals(1, hits.stream().filter("/product"::equals).count(), "只需选一次配置");
    }

    private static AppConfig.Step selectStep(String selector, String value) {
        AppConfig.Step s = new AppConfig.Step();
        s.action = "select";
        s.selector = selector;
        s.value = value;
        return s;
    }

    @Test
    void unitStepsRepeatForQuantity() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.quantity = 2;
        c.unitSteps = new ArrayList<>(List.of(
                step("goto", null, null, false, false),
                step("click", "{color}", null, false, false),
                step("click", "バッグに追加", null, false, false)));
        c.steps = new ArrayList<>(List.of(step("click", "ご注文手続き", null, false, false)));
        AutoCheckout.Outcome o = new AutoCheckout(c).run(event(sku("ナイトスカイ", "256GB")));
        assertEquals(AutoCheckout.Outcome.SUBMITTED, o);
        assertEquals(2, hits.stream().filter("/product"::equals).count(), "每台都应重新打开购买页: " + hits);
        assertEquals(7, new AutoCheckout(c).plan().size()); // 3 个步骤 × 2 台 + 1 个收尾步骤
        assertTrue(!hits.contains("placed"));
    }

    @Test
    void reportsMissingColorAndCapacity() {
        AppConfig.Checkout c = cfg(false);
        c.unitSteps = new ArrayList<>(List.of(
                step("click", "{color}", null, false, false),
                step("click", "{capacity}", null, false, false)));
        AutoCheckout co = new AutoCheckout(c);
        assertEquals(List.of("颜色", "容量"), co.missingFields(sku("", "")));
        assertEquals(List.of("容量"), co.missingFields(sku("ナイトスカイ", " ")));
        assertTrue(co.missingFields(sku("ナイトスカイ", "256GB")).isEmpty());
        // 可选步骤用到的占位符不算缺失
        c.unitSteps = new ArrayList<>(List.of(step("click", "{color}", null, true, false)));
        assertTrue(new AutoCheckout(c).missingFields(sku("", "")).isEmpty());
    }

    @Test
    void failureDumpsClickableTextsAndHtml() throws Exception {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.steps.clear();
        c.unitSteps = new ArrayList<>(List.of(
                step("goto", null, null, false, false),
                step("click", "不存在的按钮", null, false, false)));
        AutoCheckout.Outcome o = new AutoCheckout(c).run(event(sku("ナイトスカイ", "256GB")));
        assertEquals(AutoCheckout.Outcome.FAILED, o);
        try (var files = Files.list(tmp.resolve("shots"))) {
            List<String> names = files.map(p -> p.getFileName().toString()).toList();
            assertTrue(names.stream().anyMatch(n -> n.endsWith(".png")), "应有截图: " + names);
            assertTrue(names.stream().anyMatch(n -> n.endsWith(".html")), "应有页面源码: " + names);
        }
    }

    @Test
    void prefersElementWhoseTextIsExactlyTheLabel() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.steps.clear();
        c.unitSteps = new ArrayList<>(List.of(
                step("goto", null, base() + "/exact", false, false),
                step("click", "ブラック", null, false, false)));
        assertEquals(AutoCheckout.Outcome.SUBMITTED, new AutoCheckout(c).run(event(sku("ブラック", "256GB"))));
        assertTrue(hits.contains("/right") && !hits.contains("/wrong"), "应点中文字完全相同的那个: " + hits);
    }

    @Test
    void fallsBackToScriptClickWhenCovered() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.steps.clear();
        c.unitSteps = new ArrayList<>(List.of(
                step("goto", null, base() + "/covered", false, false),
                step("click", "押せないボタン", null, false, false)));
        assertEquals(AutoCheckout.Outcome.SUBMITTED, new AutoCheckout(c).run(event(sku("ブラック", "256GB"))));
        assertTrue(hits.contains("/forced"), "被遮挡时应改用脚本点击: " + hits);
    }

    /** 用要发给用户的那份示例配置里的步骤，在复刻真实结构的页面上跑一遍，返回依次被选中的控件。 */
    private AutoCheckout.Outcome runShippedStepsOnRealPage(String query, List<String> clickedOut) throws Exception {
        AppConfig parsed = com.stockmonitor.config.ConfigManager.parse(
                Files.readString(Path.of("application-example.yml"), StandardCharsets.UTF_8));
        AppConfig.Checkout c = parsed.purchase.checkout;
        AppConfig.Checkout base = cfg(false);
        c.headless = true;
        c.executablePath = base.executablePath;
        c.profileDir = base.profileDir;
        c.screenshotDir = base.screenshotDir;
        c.defaultTimeoutMs = 3000;
        c.unitSteps.get(0).value = base() + "/real" + query; // 整套配置（含购物袋里选数量、点「ご注文手続き」）一起跑
        Sku sku = sku("ブラック", "256GB");
        sku.model = "iPhone 18 Pro";
        AutoCheckout.Outcome o = new AutoCheckout(c).run(event(sku));
        hits.stream().filter(h -> h.startsWith("/rec?n=")).map(h -> h.substring("/rec?n=".length())).forEach(clickedOut::add);
        return o;
    }

    @Test
    void shippedStepsWorkOnRealStructure() throws Exception {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        List<String> clicked = new ArrayList<>();
        assertEquals(AutoCheckout.Outcome.SUBMITTED, runShippedStepsOnRealPage("", clicked));
        // 型号 → 颜色(ブラック) → 容量(256 GB) → 下取りを利用しない → 一括払い（不是分期）→ SIMフリー → AppleCare不加 → 続ける
        assertEquals(List.of("m1", "c-black", "cap-256", "t-no", "pay-full", "sim-free", "care-no", "add-to-bag"), clicked);
        // 加入购物袋后：数量选成 2，再点「ご注文手続き」到结算页；全程没有任何「下单」动作
        assertTrue(hits.contains("/qty?v=2"), "购物袋里数量应被选为 2: " + hits);
        assertTrue(hits.contains("/checkout"), "应已走到结算页: " + hits);
        assertTrue(!hits.contains("placed"), "不能下单: " + hits);
    }

    @Test
    void shippedStepsWorkWhenCarrierComesBeforePayment() throws Exception {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        List<String> clicked = new ArrayList<>();
        assertEquals(AutoCheckout.Outcome.SUBMITTED, runShippedStepsOnRealPage("?o=simfirst", clicked));
        assertEquals(List.of("m1", "c-black", "cap-256", "t-no", "sim-free", "pay-full", "care-no", "add-to-bag"), clicked);
        assertTrue(hits.contains("/qty?v=2") && hits.contains("/checkout"), "应走到结算页: " + hits);
    }

    @Test
    void clickingADisabledOptionFailsHonestly() {
        Assumptions.assumeTrue(chromium() != null, "没有可用的 Chromium，跳过");
        AppConfig.Checkout c = cfg(false);
        c.steps.clear();
        // 不先选型号就直接点颜色：此时颜色是灰色禁用的，必须如实报错，而不是假装成功
        AppConfig.Step color = step("click", "ブラック", null, false, false);
        color.within = "[data-analytics-section='dimensionColor']";
        c.unitSteps = new ArrayList<>(List.of(step("goto", null, base() + "/real", false, false), color));
        assertEquals(AutoCheckout.Outcome.FAILED, new AutoCheckout(c).run(event(sku("ブラック", "256GB"))));
        assertTrue(hits.stream().noneMatch(h -> h.startsWith("/rec?n=c-")), "不应有任何颜色被选中: " + hits);
    }
}
