package com.stockmonitor.model;

import java.util.Objects;

/** 一个待监控的「颜色 + 容量」组合（以 Apple 部件号标识）。 */
public class Sku {
    public String partNumber;
    public String name;
    public String color;
    public String capacity;
    public boolean enabled = true;
    /** 可选：有货时打开的购买链接；留空则使用型号产品页。 */
    public String buyUrl;

    public Sku() {
    }

    public Sku(String partNumber, String name) {
        this.partNumber = partNumber;
        this.name = name;
    }

    public String displayName() {
        if (name == null || name.isBlank()) {
            return partNumber;
        }
        // 名称里已经带了部件号时不再重复拼接
        return partNumber == null || partNumber.isBlank() || name.contains(partNumber) ? name : name + " (" + partNumber + ")";
    }

    @Override
    public boolean equals(Object o) {
        return o instanceof Sku other && Objects.equals(partNumber, other.partNumber);
    }

    @Override
    public int hashCode() {
        return Objects.hashCode(partNumber);
    }

    @Override
    public String toString() {
        return displayName();
    }
}
