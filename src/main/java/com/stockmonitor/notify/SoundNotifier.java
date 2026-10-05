package com.stockmonitor.notify;

import com.stockmonitor.model.AvailabilityEvent;

import javax.sound.sampled.AudioInputStream;
import javax.sound.sampled.AudioSystem;
import javax.sound.sampled.Clip;
import java.awt.Toolkit;
import java.io.File;

public class SoundNotifier implements Notifier {
    private final String soundFile;

    public SoundNotifier(String soundFile) {
        this.soundFile = soundFile;
    }

    @Override
    public String name() {
        return "提示音";
    }

    @Override
    public void notify(AvailabilityEvent e) throws Exception {
        if (soundFile != null && !soundFile.isBlank() && new File(soundFile).isFile()) {
            try (AudioInputStream in = AudioSystem.getAudioInputStream(new File(soundFile))) {
                Clip clip = AudioSystem.getClip();
                clip.open(in);
                clip.start();
                Thread.sleep(Math.min(10_000, clip.getMicrosecondLength() / 1000));
                clip.close();
                return;
            }
        }
        for (int i = 0; i < 5; i++) {
            try {
                Toolkit.getDefaultToolkit().beep();
            } catch (Throwable ignored) {
                System.out.print('\u0007');
            }
            Thread.sleep(300);
        }
    }
}
