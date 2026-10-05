package com.stockmonitor.model;

public enum StockState {
    AVAILABLE("有货"),
    UNAVAILABLE("无货"),
    UNKNOWN("无法判断");

    private final String label;

    StockState(String label) {
        this.label = label;
    }

    public String label() {
        return label;
    }
}
