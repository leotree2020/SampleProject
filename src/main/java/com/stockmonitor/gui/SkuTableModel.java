package com.stockmonitor.gui;

import com.stockmonitor.model.CheckResult;
import com.stockmonitor.model.Sku;
import com.stockmonitor.model.StockState;

import javax.swing.table.AbstractTableModel;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** SKU 表格：启用 / 名称 / 部件号 可编辑，状态 / 详情 / 时间 / 耗时 由监控结果刷新。 */
final class SkuTableModel extends AbstractTableModel {
    static final String[] COLUMNS = {"启用", "名称", "部件号", "状态", "详情", "上次检查", "耗时(ms)"};
    private static final DateTimeFormatter TIME = DateTimeFormatter.ofPattern("HH:mm:ss");

    private List<Sku> skus = List.of();
    private final Map<Sku, CheckResult> results = new HashMap<>();
    private final Map<Sku, String> checkedAt = new HashMap<>();

    void setSkus(List<Sku> skus) {
        this.skus = skus;
        results.clear();
        checkedAt.clear();
        fireTableDataChanged();
    }

    List<Sku> skus() {
        return skus;
    }

    Sku skuAt(int row) {
        return skus.get(row);
    }

    void update(CheckResult r) {
        results.put(r.sku(), r);
        checkedAt.put(r.sku(), LocalTime.now().format(TIME));
        int row = skus.indexOf(r.sku());
        if (row >= 0) {
            fireTableRowsUpdated(row, row);
        }
    }

    StockState stateAt(int row) {
        CheckResult r = results.get(skus.get(row));
        return r == null ? null : r.isSuccess() ? r.state() : StockState.UNKNOWN;
    }

    boolean failedAt(int row) {
        CheckResult r = results.get(skus.get(row));
        return r != null && !r.isSuccess();
    }

    @Override
    public int getRowCount() {
        return skus.size();
    }

    @Override
    public int getColumnCount() {
        return COLUMNS.length;
    }

    @Override
    public String getColumnName(int c) {
        return COLUMNS[c];
    }

    @Override
    public Class<?> getColumnClass(int c) {
        return c == 0 ? Boolean.class : String.class;
    }

    @Override
    public boolean isCellEditable(int row, int c) {
        return c <= 2;
    }

    @Override
    public Object getValueAt(int row, int c) {
        Sku s = skus.get(row);
        CheckResult r = results.get(s);
        return switch (c) {
            case 0 -> s.enabled;
            case 1 -> s.name == null ? "" : s.name;
            case 2 -> s.partNumber == null ? "" : s.partNumber;
            case 3 -> r == null ? "—" : r.isSuccess() ? r.state().label() : "查询失败";
            case 4 -> r == null ? "" : r.isSuccess() ? describe(r) : r.error();
            case 5 -> checkedAt.getOrDefault(s, "");
            default -> r == null ? "" : String.valueOf(r.latencyMs());
        };
    }

    private static String describe(CheckResult r) {
        String d = r.detail() == null ? "" : r.detail();
        return r.pickupStores().isEmpty() ? d : d + " | 取货: " + String.join(", ", r.pickupStores());
    }

    @Override
    public void setValueAt(Object v, int row, int c) {
        Sku s = skus.get(row);
        switch (c) {
            case 0 -> s.enabled = (Boolean) v;
            case 1 -> s.name = String.valueOf(v).trim();
            case 2 -> s.partNumber = String.valueOf(v).replaceAll("\\s+", "").toUpperCase(java.util.Locale.ROOT);
            default -> {
            }
        }
        fireTableRowsUpdated(row, row);
    }
}
