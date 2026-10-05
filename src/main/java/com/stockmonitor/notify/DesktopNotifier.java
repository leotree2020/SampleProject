package com.stockmonitor.notify;

import com.stockmonitor.model.AvailabilityEvent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.awt.GraphicsEnvironment;
import java.awt.Image;
import java.awt.SystemTray;
import java.awt.TrayIcon;
import java.awt.image.BufferedImage;

/** 系统托盘通知；无图形环境（服务器/headless）下自动禁用。 */
public class DesktopNotifier implements Notifier {
    private static final Logger log = LoggerFactory.getLogger(DesktopNotifier.class);
    private TrayIcon trayIcon;

    public static boolean supported() {
        try {
            return !GraphicsEnvironment.isHeadless() && SystemTray.isSupported();
        } catch (Throwable t) {
            return false;
        }
    }

    @Override
    public String name() {
        return "桌面通知";
    }

    @Override
    public synchronized void notify(AvailabilityEvent e) throws Exception {
        if (trayIcon == null) {
            Image img = new BufferedImage(16, 16, BufferedImage.TYPE_INT_ARGB);
            trayIcon = new TrayIcon(img, "iPhone 库存监控");
            trayIcon.setImageAutoSize(true);
            SystemTray.getSystemTray().add(trayIcon);
            log.debug("系统托盘图标已添加");
        }
        trayIcon.displayMessage(e.title(), e.message(), TrayIcon.MessageType.INFO);
    }
}
