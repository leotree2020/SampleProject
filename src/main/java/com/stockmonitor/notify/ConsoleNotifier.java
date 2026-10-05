package com.stockmonitor.notify;

import com.stockmonitor.model.AvailabilityEvent;

public class ConsoleNotifier implements Notifier {
    private static final String RED = "\u001B[1;97;41m";
    private static final String GREEN = "\u001B[1;32m";
    private static final String RESET = "\u001B[0m";

    @Override
    public String name() {
        return "控制台";
    }

    @Override
    public void notify(AvailabilityEvent e) {
        String bar = "=".repeat(62);
        System.out.println();
        System.out.println(RED + bar + RESET);
        System.out.println(RED + "  >>> " + e.title() + " <<<  " + RESET);
        System.out.println(RED + bar + RESET);
        System.out.println(GREEN + e.message() + RESET);
        System.out.println(RED + bar + RESET);
        System.out.println();
    }
}
