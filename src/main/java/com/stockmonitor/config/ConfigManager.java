package com.stockmonitor.config;

import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.stockmonitor.model.Sku;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

/** 加载 application.yml，并每 5 秒检查文件变化以实现热更新。 */
public final class ConfigManager {
    private static final Logger log = LoggerFactory.getLogger(ConfigManager.class);

    private static final ObjectMapper YAML = new ObjectMapper(new YAMLFactory())
            .setPropertyNamingStrategy(PropertyNamingStrategies.KEBAB_CASE)
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);

    private final Path path;
    private volatile AppConfig config;
    private volatile long lastModified;
    /** 启动时选定的型号；热更新后仍保持该选择。 */
    private volatile String selectedModel;

    public ConfigManager(Path path) throws IOException {
        this.path = path;
        this.config = parse(Files.readString(path, StandardCharsets.UTF_8));
        this.lastModified = Files.getLastModifiedTime(path).toMillis();
        validate(config);
    }

    public static AppConfig parse(String yaml) throws IOException {
        AppConfig cfg = YAML.readValue(EnvExpander.expand(yaml), AppConfig.class);
        return cfg == null ? new AppConfig() : cfg;
    }

    private static void validate(AppConfig cfg) {
        if (cfg.monitor.models.isEmpty()) {
            throw new IllegalStateException("配置错误：monitor.models 为空，至少需要一个型号预设");
        }
        String mode = cfg.monitor.checkMode;
        if (!List.of("buyability", "fulfillment", "product-page").contains(mode)) {
            throw new IllegalStateException("配置错误：monitor.check-mode 不支持 '" + mode + "'");
        }
    }

    public AppConfig get() {
        return config;
    }

    public Path path() {
        return path;
    }

    public void selectModel(String key) {
        if (!config.monitor.models.containsKey(key)) {
            throw new IllegalArgumentException("未知型号: " + key + "，可选: " + config.monitor.models.keySet());
        }
        this.selectedModel = key;
    }

    public String selectedModelKey() {
        return selectedModel;
    }

    public AppConfig.ModelPreset activeModel() {
        AppConfig.ModelPreset preset = config.monitor.models.get(selectedModel);
        if (preset == null) {
            // 热更新后型号被删除：回退到第一个
            preset = config.monitor.models.values().iterator().next();
        }
        return preset;
    }

    public List<Sku> enabledSkus() {
        return activeModel().skus.stream()
                .filter(s -> s.enabled && s.partNumber != null && !s.partNumber.isBlank())
                .toList();
    }

    public void startWatching(ScheduledExecutorService scheduler) {
        scheduler.scheduleWithFixedDelay(this::reloadIfChanged, 5, 5, TimeUnit.SECONDS);
    }

    void reloadIfChanged() {
        try {
            long mtime = Files.getLastModifiedTime(path).toMillis();
            if (mtime == lastModified) {
                return;
            }
            lastModified = mtime;
            AppConfig fresh = parse(Files.readString(path, StandardCharsets.UTF_8));
            validate(fresh);
            config = fresh;
            log.info("配置已热更新：{}（当前型号 {}，启用 SKU {} 个）", path, activeModel().name, enabledSkus().size());
        } catch (Exception e) {
            log.warn("配置热更新失败，继续使用旧配置：{}", e.getMessage());
        }
    }
}
