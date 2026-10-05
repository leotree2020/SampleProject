package com.stockmonitor.gui;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.PatternLayout;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.slf4j.LoggerFactory;

import javax.swing.JTextArea;
import javax.swing.SwingUtilities;

/** 把 logback 日志同步显示到界面的日志面板。 */
final class LogPaneAppender extends AppenderBase<ILoggingEvent> {
    private static final int MAX_CHARS = 200_000;

    private final JTextArea area;
    private final PatternLayout layout;

    private LogPaneAppender(JTextArea area, PatternLayout layout) {
        this.area = area;
        this.layout = layout;
    }

    static void attach(JTextArea area) {
        LoggerContext ctx = (LoggerContext) LoggerFactory.getILoggerFactory();
        PatternLayout layout = new PatternLayout();
        layout.setContext(ctx);
        layout.setPattern("%d{HH:mm:ss} %-5level %msg%n");
        layout.start();
        LogPaneAppender appender = new LogPaneAppender(area, layout);
        appender.setContext(ctx);
        appender.start();
        ((Logger) LoggerFactory.getLogger(org.slf4j.Logger.ROOT_LOGGER_NAME)).addAppender(appender);
    }

    @Override
    protected void append(ILoggingEvent event) {
        String text = layout.doLayout(event);
        SwingUtilities.invokeLater(() -> {
            area.append(text);
            if (area.getDocument().getLength() > MAX_CHARS) {
                try {
                    area.getDocument().remove(0, MAX_CHARS / 4);
                } catch (Exception ignored) {
                }
            }
            area.setCaretPosition(area.getDocument().getLength());
        });
    }
}
