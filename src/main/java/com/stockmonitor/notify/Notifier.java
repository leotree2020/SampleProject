package com.stockmonitor.notify;

import com.stockmonitor.model.AvailabilityEvent;

public interface Notifier {
    String name();

    void notify(AvailabilityEvent event) throws Exception;
}
