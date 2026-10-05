package com.stockmonitor.gui;

import com.stockmonitor.config.AppConfig;
import com.stockmonitor.config.ConfigManager;
import com.stockmonitor.http.BrowserHeaders;
import com.stockmonitor.http.HttpClientFactory;
import com.stockmonitor.http.ProxyManager;
import com.stockmonitor.model.AvailabilityEvent;
import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;
import com.stockmonitor.monitor.AppleStoreClient;
import com.stockmonitor.monitor.StockMonitor;
import com.stockmonitor.notify.NotificationManager;
import com.stockmonitor.notify.PurchaseAssistant;
import com.stockmonitor.util.HistoryStore;
import com.stockmonitor.util.Stats;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import javax.swing.BorderFactory;
import javax.swing.Box;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JSpinner;
import javax.swing.JSplitPane;
import javax.swing.JTable;
import javax.swing.JTextArea;
import javax.swing.SpinnerNumberModel;
import javax.swing.SwingUtilities;
import javax.swing.Timer;
import javax.swing.table.DefaultTableCellRenderer;
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Component;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Font;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;

/** 图形界面：选择型号、编辑部件号、开始/停止监控、查看实时状态与日志。只监控和提醒，不下单。 */
public final class MonitorFrame extends JFrame {
    private static final Logger log = LoggerFactory.getLogger(MonitorFrame.class);
    private static final Color GREEN = new Color(0xC8F7C5);
    private static final Color GRAY = new Color(0xF2F2F2);
    private static final Color ORANGE = new Color(0xFFE0B2);

    private final ConfigManager configs;
    private final AppConfig cfg;
    private final Stats stats = new Stats();
    private final HttpClientFactory http;
    private final AppleStoreClient client;
    private final NotificationManager notifications;
    private final PurchaseAssistant purchase;
    private final HistoryStore history = new HistoryStore(Path.of("data", "availability-history.csv"));

    private final SkuTableModel tableModel = new SkuTableModel();
    private final JTable table = new JTable(tableModel);
    private final JComboBox<String> modelBox = new JComboBox<>();
    private final JComboBox<String> modeBox = new JComboBox<>(new String[]{"fulfillment", "buyability", "product-page"});
    private final JSpinner baseSpinner;
    private final JSpinner jitterSpinner;
    private final JCheckBox openBrowserBox = new JCheckBox("有货时自动打开购买页");
    private final JCheckBox checkoutBox = new JCheckBox("有货时自动结账");
    private final JCheckBox submitBox = new JCheckBox("自动提交订单");
    private final JButton loginBtn = new JButton("登录 Apple ID");
    private final JButton startBtn = new JButton("▶ 开始监控");
    private final JButton stopBtn = new JButton("■ 停止");
    private final JButton onceBtn = new JButton("立即检查一次");
    private final JLabel statusLabel = new JLabel("未运行");
    private final JLabel statsLabel = new JLabel(" ");
    private final JTextArea logArea = new JTextArea();
    private final List<String> modelKeys = new ArrayList<>();

    private ScheduledExecutorService scheduler;
    private StockMonitor monitor;
    private boolean updatingModelBox;

    public MonitorFrame(ConfigManager configs, String initialModelKey) {
        super("iPhone 库存监控（日本 Apple Store）");
        this.configs = configs;
        this.cfg = configs.get();
        this.http = new HttpClientFactory(cfg.http, new ProxyManager(cfg.proxy));
        this.client = new AppleStoreClient(configs, http, new BrowserHeaders(cfg.http.userAgents, cfg.http.extraHeaders));
        this.notifications = new NotificationManager(cfg.notify, stats);
        this.purchase = new PurchaseAssistant(cfg.purchase);
        this.baseSpinner = new JSpinner(new SpinnerNumberModel(cfg.monitor.interval.baseSeconds, 1.0, 600.0, 1.0));
        this.jitterSpinner = new JSpinner(new SpinnerNumberModel(cfg.monitor.interval.jitterSeconds, 0.0, 120.0, 1.0));

        buildUi();
        LogPaneAppender.attach(logArea);
        loadModels(initialModelKey);
        setDefaultCloseOperation(DO_NOTHING_ON_CLOSE);
        addWindowListener(new java.awt.event.WindowAdapter() {
            @Override
            public void windowClosing(java.awt.event.WindowEvent e) {
                shutdown();
            }
        });
        setSize(1100, 700);
        setLocationRelativeTo(null);
        new Timer(1000, e -> statsLabel.setText(stats.summary())).start();
    }

    private void buildUi() {
        JPanel top = new JPanel(new FlowLayout(FlowLayout.LEFT, 8, 6));
        top.add(new JLabel("型号:"));
        top.add(modelBox);
        top.add(new JLabel("检查模式:"));
        modeBox.setSelectedItem(cfg.monitor.checkMode);
        top.add(modeBox);
        top.add(new JLabel("间隔(秒):"));
        top.add(baseSpinner);
        top.add(new JLabel("±"));
        top.add(jitterSpinner);
        openBrowserBox.setSelected(cfg.purchase.autoOpenBrowser);
        top.add(openBrowserBox);
        checkoutBox.setSelected(cfg.purchase.checkout.enabled);
        submitBox.setSelected(cfg.purchase.checkout.autoSubmit);
        top.add(checkoutBox);
        top.add(submitBox);

        JPanel buttons = new JPanel(new FlowLayout(FlowLayout.LEFT, 8, 6));
        buttons.add(startBtn);
        buttons.add(stopBtn);
        buttons.add(onceBtn);
        buttons.add(Box.createHorizontalStrut(16));
        JButton add = new JButton("添加 SKU");
        JButton remove = new JButton("删除选中");
        JButton testNotify = new JButton("测试提醒");
        JButton openPage = new JButton("打开购买页");
        buttons.add(add);
        buttons.add(remove);
        buttons.add(testNotify);
        buttons.add(openPage);
        buttons.add(Box.createHorizontalStrut(16));
        buttons.add(loginBtn);
        stopBtn.setEnabled(false);

        JPanel north = new JPanel(new BorderLayout());
        north.add(top, BorderLayout.NORTH);
        north.add(buttons, BorderLayout.SOUTH);

        table.setRowHeight(26);
        table.setFillsViewportHeight(true);
        int[] widths = {50, 220, 110, 100, 70, 80, 340, 80, 70};
        for (int i = 0; i < widths.length; i++) {
            table.getColumnModel().getColumn(i).setPreferredWidth(widths[i]);
        }
        DefaultTableCellRenderer stateRenderer = new DefaultTableCellRenderer() {
            @Override
            public Component getTableCellRendererComponent(JTable t, Object v, boolean sel, boolean focus, int row, int col) {
                Component c = super.getTableCellRendererComponent(t, v, sel, focus, row, col);
                int m = t.convertRowIndexToModel(row);
                StockState st = tableModel.stateAt(m);
                if (!sel) {
                    c.setBackground(st == null ? Color.WHITE
                            : tableModel.failedAt(m) || st == StockState.UNKNOWN ? ORANGE
                            : st == StockState.AVAILABLE ? GREEN : GRAY);
                    c.setForeground(Color.BLACK);
                }
                if (st == StockState.AVAILABLE) {
                    c.setFont(c.getFont().deriveFont(Font.BOLD));
                }
                return c;
            }
        };
        for (int i = 1; i < SkuTableModel.COLUMNS.length; i++) {
            table.getColumnModel().getColumn(i).setCellRenderer(stateRenderer);
        }

        logArea.setEditable(false);
        logArea.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 12));
        JScrollPane logScroll = new JScrollPane(logArea);
        logScroll.setBorder(BorderFactory.createTitledBorder("日志"));
        JScrollPane tableScroll = new JScrollPane(table);
        JSplitPane split = new JSplitPane(JSplitPane.VERTICAL_SPLIT, tableScroll, logScroll);
        split.setResizeWeight(0.5);

        JPanel south = new JPanel(new BorderLayout());
        south.setBorder(BorderFactory.createEmptyBorder(4, 8, 4, 8));
        statusLabel.setFont(statusLabel.getFont().deriveFont(Font.BOLD));
        south.add(statusLabel, BorderLayout.WEST);
        south.add(statsLabel, BorderLayout.EAST);

        setLayout(new BorderLayout());
        add(north, BorderLayout.NORTH);
        add(split, BorderLayout.CENTER);
        add(south, BorderLayout.SOUTH);

        modelBox.addActionListener(e -> {
            if (!updatingModelBox && modelBox.getSelectedIndex() >= 0) {
                switchModel(modelKeys.get(modelBox.getSelectedIndex()));
            }
        });
        modeBox.addActionListener(e -> cfg.monitor.checkMode = (String) modeBox.getSelectedItem());
        baseSpinner.addChangeListener(e -> cfg.monitor.interval.baseSeconds = ((Number) baseSpinner.getValue()).doubleValue());
        jitterSpinner.addChangeListener(e -> cfg.monitor.interval.jitterSeconds = ((Number) jitterSpinner.getValue()).doubleValue());
        openBrowserBox.addActionListener(e -> cfg.purchase.autoOpenBrowser = openBrowserBox.isSelected());
        checkoutBox.addActionListener(e -> {
            cfg.purchase.checkout.enabled = checkoutBox.isSelected();
            if (checkoutBox.isSelected() && !java.nio.file.Files.isDirectory(Path.of(cfg.purchase.checkout.profileDir))) {
                JOptionPane.showMessageDialog(this, "还没有保存过登录会话。请先点「登录 Apple ID」，在弹出的浏览器里登录并确认地址和支付方式。",
                        "提示", JOptionPane.INFORMATION_MESSAGE);
            }
        });
        submitBox.addActionListener(e -> {
            if (!submitBox.isSelected()) {
                cfg.purchase.checkout.autoSubmit = false;
                return;
            }
            int ok = JOptionPane.showConfirmDialog(this,
                    "开启后，检测到有货时程序会自动点击最后的「确认下单」，并使用你账户里已保存的支付方式扣款。\n"
                            + "请确认：部件号、颜色、容量、配送地址和支付方式都正确，且你确实要购买。\n\n确定开启自动提交订单吗？",
                    "确认自动提交订单", JOptionPane.YES_NO_OPTION, JOptionPane.WARNING_MESSAGE);
            cfg.purchase.checkout.autoSubmit = ok == JOptionPane.YES_OPTION;
            submitBox.setSelected(cfg.purchase.checkout.autoSubmit);
        });
        loginBtn.addActionListener(e -> {
            Thread t = new Thread(() -> purchase.checkout().interactiveLogin(client.productPageUrl()), "apple-login");
            t.setDaemon(true);
            t.start();
        });
        startBtn.addActionListener(e -> startMonitoring());
        stopBtn.addActionListener(e -> stopMonitoring());
        onceBtn.addActionListener(e -> checkOnce());
        add.addActionListener(e -> addSku());
        remove.addActionListener(e -> removeSelected());
        testNotify.addActionListener(e -> testNotify());
        openPage.addActionListener(e -> openBuyPage());
    }

    private void loadModels(String initialKey) {
        updatingModelBox = true;
        modelBox.removeAllItems();
        modelKeys.clear();
        cfg.monitor.models.forEach((key, preset) -> {
            modelKeys.add(key);
            modelBox.addItem(preset.name + "  [" + key + "]");
        });
        updatingModelBox = false;
        int idx = Math.max(0, modelKeys.indexOf(initialKey));
        modelBox.setSelectedIndex(idx);
        switchModel(modelKeys.get(idx));
    }

    private void switchModel(String key) {
        if (monitor != null) {
            stopMonitoring();
        }
        configs.selectModel(key);
        tableModel.setSkus(configs.activeModel().skus);
        setStatus("已选择 " + configs.activeModel().name + "，请确认部件号后点击「开始监控」", Color.DARK_GRAY);
    }

    private void startMonitoring() {
        commitEdit();
        if (configs.enabledSkus().isEmpty()) {
            JOptionPane.showMessageDialog(this, "没有启用的 SKU，请勾选并填写部件号。", "提示", JOptionPane.WARNING_MESSAGE);
            return;
        }
        if (cfg.purchase.checkout.enabled) {
            StringBuilder problems = new StringBuilder();
            for (Sku s : configs.enabledSkus()) {
                List<String> missing = purchase.checkout().missingFields(s);
                if (!missing.isEmpty()) {
                    problems.append("· ").append(s.displayName()).append("：缺少 ").append(String.join("、", missing)).append('\n');
                }
            }
            if (problems.length() > 0) {
                JOptionPane.showMessageDialog(this, "已勾选「有货时自动结账」，但下面的 SKU 还没填写自动选择需要的内容：\n\n" + problems
                        + "\n请在表格里双击对应的格子填写（内容要和官网页面上的选项文字完全一致），或先取消勾选「有货时自动结账」。",
                        "还不能开始", JOptionPane.WARNING_MESSAGE);
                return;
            }
        }
        scheduler = Executors.newScheduledThreadPool(2, r -> {
            Thread t = new Thread(r, "scheduler");
            t.setDaemon(true);
            return t;
        });
        monitor = new StockMonitor(configs, client, notifications, purchase, history, stats, scheduler);
        monitor.addListener(this::onResult);
        monitor.start();
        startBtn.setEnabled(false);
        stopBtn.setEnabled(true);
        modelBox.setEnabled(false);
        setStatus("监控中：" + configs.activeModel().name + "（" + configs.enabledSkus().size() + " 个 SKU）", new Color(0x2E7D32));
        log.info("开始监控 {}，模式 {}", configs.activeModel().name, cfg.monitor.checkMode);
    }

    private void stopMonitoring() {
        if (monitor != null) {
            monitor.stop();
            scheduler.shutdownNow();
            monitor = null;
        }
        startBtn.setEnabled(true);
        stopBtn.setEnabled(false);
        modelBox.setEnabled(true);
        setStatus("已停止", Color.DARK_GRAY);
        log.info("已停止监控");
    }

    private void checkOnce() {
        commitEdit();
        List<Sku> skus = configs.enabledSkus();
        if (skus.isEmpty()) {
            return;
        }
        onceBtn.setEnabled(false);
        Thread t = new Thread(() -> {
            try {
                for (Sku s : skus) {
                    onResult(client.check(s));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                SwingUtilities.invokeLater(() -> onceBtn.setEnabled(true));
            }
        }, "check-once");
        t.setDaemon(true);
        t.start();
    }

    private void onResult(CheckResult r) {
        SwingUtilities.invokeLater(() -> {
            tableModel.update(r);
            if (r.isSuccess() && r.isAvailable()) {
                setStatus("★ 有货！" + r.sku().displayName(), new Color(0xC62828));
            }
        });
    }

    private void addSku() {
        commitEdit();
        Sku s = new Sku("", "新 SKU");
        configs.activeModel().skus.add(s);
        tableModel.setSkus(configs.activeModel().skus);
        int row = tableModel.getRowCount() - 1;
        table.editCellAt(row, 2);
        table.changeSelection(row, 2, false, false);
    }

    private void removeSelected() {
        commitEdit();
        int[] rows = table.getSelectedRows();
        for (int i = rows.length - 1; i >= 0; i--) {
            configs.activeModel().skus.remove(table.convertRowIndexToModel(rows[i]));
        }
        tableModel.setSkus(configs.activeModel().skus);
    }

    private void testNotify() {
        Sku sku = selectedOrFirstSku();
        AvailabilityEvent ev = new AvailabilityEvent(CheckResult.of(sku, StockState.AVAILABLE, "テスト", List.of()),
                client.buyUrl(sku), LocalDateTime.now(), true);
        Thread t = new Thread(() -> notifications.sendTest(ev), "test-notify");
        t.setDaemon(true);
        t.start();
    }

    private void openBuyPage() {
        Sku sku = selectedOrFirstSku();
        purchase.open(new AvailabilityEvent(CheckResult.of(sku, StockState.AVAILABLE, "", List.of()),
                client.buyUrl(sku), LocalDateTime.now(), true));
    }

    private Sku selectedOrFirstSku() {
        int row = table.getSelectedRow();
        if (row >= 0) {
            return tableModel.skuAt(table.convertRowIndexToModel(row));
        }
        return tableModel.skus().isEmpty() ? new Sku("TEST", "测试 SKU") : tableModel.skus().get(0);
    }

    private void commitEdit() {
        if (table.isEditing()) {
            table.getCellEditor().stopCellEditing();
        }
    }

    private void setStatus(String text, Color color) {
        statusLabel.setText(text);
        statusLabel.setForeground(color);
    }

    private void shutdown() {
        if (monitor != null) {
            monitor.stop();
            scheduler.shutdownNow();
        }
        notifications.shutdown();
        http.shutdown();
        dispose();
        System.exit(0);
    }

    /** 在 EDT 中创建并显示窗口。 */
    public static void launch(ConfigManager configs, String initialModelKey) {
        SwingUtilities.invokeLater(() -> {
            try {
                javax.swing.UIManager.setLookAndFeel(javax.swing.UIManager.getSystemLookAndFeelClassName());
            } catch (Exception ignored) {
            }
            MonitorFrame f = new MonitorFrame(configs, initialModelKey);
            f.setMinimumSize(new Dimension(800, 500));
            f.setVisible(true);
        });
    }
}
