package com.stockmonitor.notify;

import com.stockmonitor.config.AppConfig;
import com.stockmonitor.model.AvailabilityEvent;
import jakarta.mail.Authenticator;
import jakarta.mail.Message;
import jakarta.mail.PasswordAuthentication;
import jakarta.mail.Session;
import jakarta.mail.Transport;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Properties;

public class EmailNotifier implements Notifier {
    private final AppConfig.Email cfg;
    private final Session session;

    public EmailNotifier(AppConfig.Email cfg) {
        this.cfg = cfg;
        Properties p = new Properties();
        p.put("mail.smtp.host", cfg.smtpHost);
        p.put("mail.smtp.port", String.valueOf(cfg.smtpPort));
        p.put("mail.smtp.auth", "true");
        p.put("mail.smtp.connectiontimeout", "15000");
        p.put("mail.smtp.timeout", "20000");
        if (cfg.useSsl) {
            p.put("mail.smtp.ssl.enable", "true");
        } else {
            p.put("mail.smtp.starttls.enable", "true");
            p.put("mail.smtp.starttls.required", "true");
        }
        this.session = Session.getInstance(p, new Authenticator() {
            @Override
            protected PasswordAuthentication getPasswordAuthentication() {
                return new PasswordAuthentication(cfg.username, cfg.password);
            }
        });
    }

    @Override
    public String name() {
        return "邮件";
    }

    @Override
    public void notify(AvailabilityEvent e) throws Exception {
        MimeMessage msg = new MimeMessage(session);
        msg.setFrom(new InternetAddress(cfg.from == null || cfg.from.isBlank() ? cfg.username : cfg.from));
        for (String to : cfg.to) {
            msg.addRecipient(Message.RecipientType.TO, new InternetAddress(to));
        }
        msg.setSubject(cfg.subject + " - " + e.sku().displayName(), StandardCharsets.UTF_8.name());
        msg.setText(e.message(), StandardCharsets.UTF_8.name());
        msg.setSentDate(new Date());
        Transport.send(msg);
    }
}
