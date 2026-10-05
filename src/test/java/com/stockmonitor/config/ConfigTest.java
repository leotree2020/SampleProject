package com.stockmonitor.config;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConfigTest {
    @Test
    void envExpansion() {
        Map<String, String> env = Map.of("A", "x$y");
        assertEquals("v=x$y, d=def, e=", EnvExpander.expand("v=${A}, d=${B:def}, e=${C}", env));
    }

    @Test
    void exampleConfigParses() throws Exception {
        AppConfig cfg = ConfigManager.parse(Files.readString(Path.of("application-example.yml"), StandardCharsets.UTF_8));
        assertEquals("https://www.apple.com/jp", cfg.monitor.baseUrl);
        assertEquals("iphone-duo", cfg.monitor.activeModel);
        AppConfig.ModelPreset duo = cfg.monitor.models.get("iphone-duo");
        assertEquals("/shop/buy-iphone/iphone-duo", duo.productPagePath);
        assertEquals(1, duo.skus.size());
        assertEquals("MK244J/A", duo.skus.get(0).partNumber);
        assertEquals("スターホワイト", duo.skus.get(0).color);
        assertEquals("256GB", duo.skus.get(0).capacity);
        assertTrue(duo.skus.get(0).enabled);
        assertEquals("buyability", cfg.monitor.checkMode);
        assertTrue(cfg.purchase.autoOpenBrowser);
        // 固定的自动结账流程：开启、买 2 台、到结算页面停下（不自动提交订单）
        AppConfig.Checkout co = cfg.purchase.checkout;
        assertTrue(co.enabled);
        assertFalse(co.autoSubmit);
        assertEquals(1, co.quantity);
        assertEquals(2, co.steps.size());
        assertEquals("select", co.steps.get(0).action);
        assertEquals("2", co.steps.get(0).value);
        assertEquals("click", co.steps.get(1).action);
        assertTrue(co.steps.stream().noneMatch(s -> s.submit)); // 默认流程里没有任何「确认下单」步骤
        List<String> texts = co.unitSteps.stream().map(s -> s.text == null ? s.action : s.text).toList();
        String pay = "一括あと払いプラン|一括払い";
        assertEquals(List.of("goto", "{model}", "{color}", "{capacity}", "下取りを利用しない", pay, "SIMフリー", pay,
                "SIMフリー", "AppleCareによる保証を追加しない", "続ける|バッグに追加", "wait-url"), texts);
        // 加入购物袋这一步默认自动点；如被 Apple 拒绝可改成 manual: true
        assertTrue(co.unitSteps.stream().noneMatch(s -> s.manual));
        // 支付方式只匹配「一括」，绝不能匹配「ペイディあと払い」分期
        assertTrue(!java.util.regex.Pattern.compile(pay).matcher("ペイディあと払いプランApple専用 7,077円/月の36回払い").find());
        AppConfig.Step payStep = co.unitSteps.stream().filter(s -> pay.equals(s.text)).findFirst().orElseThrow();
        assertEquals("[data-analytics-section='paymentOptions']", payStep.within);
        AppConfig.ModelPreset pro = cfg.monitor.models.get("iphone-18-pro");
        assertEquals("iPhone 18 Pro", pro.skus.get(0).model);
        assertEquals("ブラック", pro.skus.get(0).color);
        assertEquals("R079", cfg.monitor.stores.get(0));
    }
}
