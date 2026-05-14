#!/usr/bin/env python3
"""
Realistisches Fahrspiel  –  BeamNG-inspiriert
==============================================

Starten:
    pip install -r requirements.txt
    python main.py

Steuerung (PS5 DualSense):
    R2            Gaspedal
    L2            Bremse
    Linker Stick  Lenken
    Kreis         Handbremse
    R1 / L1       Hoch-/Runterschalten
    Dreieck       Fahrzeug zurücksetzen
    Touchpad      Kamera wechseln
    Options       Pause

Tastatur (Fallback):
    W / Pfeil-Hoch     Gas
    S / Pfeil-Runter   Bremse
    A/D / Pfeile       Lenken
    Leertaste          Handbremse
    E / Q              Hoch-/Runterschalten
    R                  Zurücksetzen
    C                  Kamera
    P                  Pause
    F11                Vollbild
"""

import sys
import os

# Make sure we can import local modules
sys.path.insert(0, os.path.dirname(__file__))

from game import DrivingGame


def main():
    print("=" * 60)
    print("  Realistisches Fahrspiel  –  Powered by Panda3D + Bullet")
    print("=" * 60)
    print()
    print("Starte Spiel …")

    app = DrivingGame()
    app.run()


if __name__ == "__main__":
    main()
