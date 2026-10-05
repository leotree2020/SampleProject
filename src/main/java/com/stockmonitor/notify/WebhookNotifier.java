package com.stockmonitor.notify;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import okhttp3.MediaType;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;

import java.io.IOException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** 机器人 Webhook：企业微信 / 钉钉 / 飞书 / Slack / Discord / Telegram，填了哪个就推送哪个。 */
public class WebhookNotifier implements Notifier {
    private static final MediaType JSON_TYPE = MediaType.get("application/json; charset=utf-8");
    private static final ObjectMapper JSON = new ObjectMapper();

    private final AppConfig.Webhook cfg;
    private final OkHttpClient client = new OkHttpClient.Builder()
            .callTimeout(Duration.ofSeconds(20))
            .build();

    public WebhookNotifier(AppConfig.Webhook cfg) {
        this.cfg = cfg;
    }

    public boolean hasTargets() {
        return notBlank(cfg.wechatWork) || notBlank(cfg.dingtalk) || notBlank(cfg.feishu)
                || notBlank(cfg.slack) || notBlank(cfg.discord)
                || (notBlank(cfg.telegramBotToken) && notBlank(cfg.telegramChatId));
    }

    @Override
    public String name() {
        return "Webhook";
    }

    @Override
    public void notify(AvailabilityEvent e) throws Exception {
        String text = e.title() + "\n" + e.message();
        List<String> errors = new ArrayList<>();
        send(cfg.wechatWork, Map.of("msgtype", "text", "text", Map.of("content", text)), "企业微信", errors);
        send(cfg.dingtalk, Map.of("msgtype", "text", "text", Map.of("content", text)), "钉钉", errors);
        send(cfg.feishu, Map.of("msg_type", "text", "content", Map.of("text", text)), "飞书", errors);
        send(cfg.slack, Map.of("text", text), "Slack", errors);
        send(cfg.discord, Map.of("content", text), "Discord", errors);
        if (notBlank(cfg.telegramBotToken) && notBlank(cfg.telegramChatId)) {
            send("https://api.telegram.org/bot" + cfg.telegramBotToken + "/sendMessage",
                    Map.of("chat_id", cfg.telegramChatId, "text", text), "Telegram", errors);
        }
        if (!errors.isEmpty()) {
            throw new IOException(String.join("; ", errors));
        }
    }

    private void send(String url, Object payload, String label, List<String> errors) {
        if (!notBlank(url)) {
            return;
        }
        try {
            RequestBody body = RequestBody.create(JSON.writeValueAsString(payload), JSON_TYPE);
            try (Response resp = client.newCall(new Request.Builder().url(url).post(body).build()).execute()) {
                if (!resp.isSuccessful()) {
                    errors.add(label + " HTTP " + resp.code());
                }
            }
        } catch (Exception ex) {
            errors.add(label + " " + ex.getMessage());
        }
    }

    private static boolean notBlank(String s) {
        return s != null && !s.isBlank();
    }
}
