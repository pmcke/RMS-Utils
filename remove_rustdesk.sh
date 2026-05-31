#!/usr/bin/env bash

sudo apt remove rustdesk
sudo apt purge rustdesk
sudo apt autoremove
rm -rf ~/.config/rustdesk
