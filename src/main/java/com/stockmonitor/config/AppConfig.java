package com.stockmonitor.config;

import com.stockmonitor.model.Sku;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** application.yml 的映射（YAML 字段使用 kebab-case，如 base-url ↔ baseUrl）。 */
public class AppConfig {
    public Monitor monitor = new Monitor();
    public Http http = new Http();
    public Proxy proxy = new Proxy();
    public Notify notify = new Notify();
    public Purchase purchase = new Purchase();

    public static class Monitor {
        public String region = "jp";
        public String baseUrl = "https://www.apple.com/jp";
        public String buyabilityPath = "/shop/buyability-message";
        public String fulfillmentPath = "/shop/fulfillment-messages";
        /** buyability | fulfillment | product-page */
        public String checkMode = "buyability";
        /** 日本邮编（如 100-0005），fulfillment 模式下用于查询配送与附近门店。 */
        public String postalCode = "";
        /** 门店号（如 R079 = Apple 銀座），fulfillment 模式下查询到店取货。 */
        public List<String> stores = new ArrayList<>();
        public Interval interval = new Interval();
        public Retry retry = new Retry();
        public Cooldown cooldown = new Cooldown();
        public int concurrency = 2;
        /** 0 = 仅在「无货→有货」时提醒一次；>0 = 持续有货时每隔该秒数重复提醒。 */
        public long renotifySeconds = 0;
        public String activeModel = "";
        public Map<String, ModelPreset> models = new LinkedHashMap<>();
    }

    public static class ModelPreset {
        public String name;
        public String productPagePath;
        public List<Sku> skus = new ArrayList<>();
    }

    public static class Interval {
        public double baseSeconds = 5;
        public double jitterSeconds = 3;
        public double minSeconds = 2;
    }

    public static class Retry {
        public int maxAttempts = 4;
        public long backoffBaseMs = 1000;
        public double backoffMultiplier = 2.0;
        public long maxBackoffMs = 30000;
    }

    public static class Cooldown {
        public int errorThreshold = 5;
        public long afterConsecutiveErrorsMs = 60000;
    }

    public static class Http {
        public int connectTimeoutSeconds = 15;
        public int readTimeoutSeconds = 20;
        public int writeTimeoutSeconds = 20;
        public int maxIdleConnections = 10;
        public int keepAliveMinutes = 5;
        public List<String> userAgents = new ArrayList<>();
        public Map<String, String> extraHeaders = new LinkedHashMap<>();
    }

    public static class Proxy {
        public boolean enabled = false;
        /** round-robin | random */
        public String rotateStrategy = "round-robin";
        public List<String> proxies = new ArrayList<>();
    }

    public static class Notify {
        public boolean console = true;
        public boolean desktop = true;
        public boolean sound = true;
        public String soundFile = "";
        public Email email = new Email();
        public Webhook webhook = new Webhook();
    }

    public static class Email {
        public boolean enabled = false;
        public String smtpHost = "smtp.gmail.com";
        public int smtpPort = 465;
        public boolean useSsl = true;
        public String username = "";
        public String password = "";
        public String from = "";
        public List<String> to = new ArrayList<>();
        public String subject = "[在庫通知] iPhone 有货";
    }

    public static class Webhook {
        public boolean enabled = false;
        public boolean testOnStartup = false;
        public String wechatWork = "";
        public String dingtalk = "";
        public String feishu = "";
        public String slack = "";
        public String discord = "";
        public String telegramBotToken = "";
        public String telegramChatId = "";
    }

    /** 有货后的「辅助抢购」行为：自动打开购买页，由你本人在浏览器内完成加购与结账。 */
    public static class Purchase {
        public boolean autoOpenBrowser = true;
        /** 同一 SKU 每次「无货→有货」只打开一次浏览器，避免持续有货时反复弹页面。 */
        public boolean openOncePerRestock = true;
        /** 同时打开的最大标签页数（多个 SKU 同时到货时）。 */
        public int maxTabsPerRound = 3;
        /** 命中后是否停止监控该 SKU（例如只想买一台时）。 */
        public boolean stopSkuAfterHit = false;
        public Checkout checkout = new Checkout();
    }

    /**
     * 自动结账：用 Playwright 驱动一个持久化的浏览器配置文件（先用 --login 手动登录一次），
     * 到货后按 steps 依次点击。不会读取或保存你的 Apple ID 密码 / 银行卡信息。
     */
    public static class Checkout {
        public boolean enabled = false;
        /** 最后一步（submit: true）默认不执行，只停在「确认下单」按钮前；设为 true 才会真正提交订单。 */
        public boolean autoSubmit = false;
        public String profileDir = "data/browser-profile";
        /** true（默认）：每次自动结账都用全新干净的浏览器环境（相当于无痕窗口），结束后删除。登录和付款由你在结算页手动完成。 */
        public boolean freshProfile = true;
        public boolean headless = false;
        /** 可选：chrome / msedge，使用本机已安装的浏览器；留空使用 Playwright 自带 Chromium。 */
        public String channel = "";
        /** 可选：浏览器可执行文件路径（优先于 channel）。 */
        public String executablePath = "";
        public int defaultTimeoutMs = 8000;
        public String screenshotDir = "data/screenshots";
        /** 买几台：unit-steps 会重复执行这么多遍（每台走一遍完整的选配流程）。 */
        public int quantity = 1;
        /** 每台都要执行的步骤（打开购买页 → 选配置 → 続ける）；重复 quantity 遍。 */
        public List<Step> unitSteps = new ArrayList<>();
        /** 所有台数都选完后只执行一次的步骤（如进入结账页）。 */
        public List<Step> steps = new ArrayList<>();
    }

    /**
     * 结账步骤。action：goto | click | fill | select（下拉框，需 selector，value 为要选的值）| press | wait | wait-url。
     * text / value 里可用占位符 {color} {capacity} {partNumber} {name} {buyUrl}；
     * click 的 text 是正则（匹配按钮/链接/选项文字），也可以直接给 CSS selector。
     */
    public static class Step {
        public String action = "click";
        public String text;
        public String selector;
        /** 可选：只在这个 CSS 区域内查找 text，如 "[data-analytics-section='dimensionColor']"，避免点到页面其他位置的同名元素。 */
        public String within;
        public String value;
        public boolean optional = false;
        /** 标记为「提交订单」步骤，仅当 auto-submit: true 时才会执行。 */
        public boolean submit = false;
        /**
         * 半自动：程序把这个按钮用红框标出来并响铃，由你本人点击，点完（页面跳转或按钮消失）再继续后面的步骤。
         * 适合某一步在被程序控制的窗口里点不通时使用（仅对 click 有效）。
         */
        public boolean manual = false;
        public int timeoutMs = 0;
    }
}
