// A release build is a GUI program: Windows opens no terminal next to the window. The dev build
// keeps its console for the native log ([video], [onvif], …).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    oncam_desktop_lib::run();
}
