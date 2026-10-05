package com.stockmonitor.util;

import com.stockmonitor.model.CheckResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/** 将有货记录追加写入 CSV，便于复盘补货规律。 */
public class HistoryStore {
    private static final Logger log = LoggerFactory.getLogger(HistoryStore.class);
    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final Path file;

    public HistoryStore(Path file) {
        this.file = file;
    }

    public synchronized void append(CheckResult r) {
        try {
            Files.createDirectories(file.getParent());
            if (Files.notExists(file)) {
                // 带 BOM，Excel 打开不乱码
                Files.writeString(file, "﻿time,part_number,name,detail,pickup_stores\n", StandardCharsets.UTF_8);
            }
            String line = String.join(",", LocalDateTime.now().format(FMT), csv(r.sku().partNumber),
                    csv(r.sku().name), csv(r.detail()), csv(String.join(" / ", r.pickupStores()))) + "\n";
            Files.writeString(file, line, StandardCharsets.UTF_8, StandardOpenOption.APPEND);
        } catch (IOException e) {
            log.warn("写入有货历史失败：{}", e.getMessage());
        }
    }

    private static String csv(String s) {
        if (s == null) {
            return "";
        }
        return "\"" + s.replace("\"", "\"\"") + "\"";
    }
}
