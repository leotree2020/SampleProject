package com.stockmonitor.config;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
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
        assertTrue(duo.skus.get(0).partNumber.endsWith("J/A"));
        assertFalse(duo.skus.get(2).enabled);
        assertTrue(cfg.purchase.autoOpenBrowser);
        assertEquals("R079", cfg.monitor.stores.get(0));
    }
}
