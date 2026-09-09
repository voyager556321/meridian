//! Meridian — recommended stack bootstrap (Rust + gtk4-rs + libadwaita-rs).
//!
//! This is a skeleton for the async application entrypoint: GLib main loop,
//! Adw.Application, background Tokio work bridged onto the UI thread.
//!
//! Cargo deps (illustrative):
//!   gtk4, libadwaita, glib, gio, tokio, reqwest, oauth2, secret-service, rusqlite, tracing

use std::sync::Arc;

use adw::prelude::*;
use gtk::{gio, glib};

fn main() -> glib::ExitCode {
    tracing_subscriber::fmt::init();

    let app = adw::Application::builder()
        .application_id("org.gnome.Meridian")
        .flags(gio::ApplicationFlags::FLAGS_NONE)
        .build();

    app.connect_activate(|app| {
        // Shared app state (SyncEngine handle, etc.) would be constructed here.
        let runtime = Arc::new(
            tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .thread_name("meridian-net")
                .build()
                .expect("tokio runtime"),
        );

        build_ui(app, runtime);
    });

    app.run()
}

fn build_ui(app: &adw::Application, runtime: Arc<tokio::runtime::Runtime>) {
    let window = adw::ApplicationWindow::builder()
        .application(app)
        .title("Meridian")
        .default_width(1100)
        .default_height(720)
        .build();

    let toast_overlay = adw::ToastOverlay::new();
    let toolbar = adw::ToolbarView::new();
    let header = adw::HeaderBar::new();
    header.set_title_widget(Some(&adw::WindowTitle::new("Meridian", "Today")));
    toolbar.add_top_bar(&header);

    let status = gtk::Label::new(Some("Signing in…"));
    status.add_css_class("dim-label");
    toolbar.set_content(Some(&status));
    toast_overlay.set_child(Some(&toolbar));
    window.set_content(Some(&toast_overlay));

    // Kick off async auth/bootstrap on Tokio; marshal results back to GLib.
    let status_c = status.clone();
    let toast_c = toast_overlay.clone();
    runtime.spawn(async move {
        match bootstrap_session().await {
            Ok(account) => {
                let msg = format!("Signed in as {account}");
                glib::MainContext::default().invoke(move || {
                    status_c.set_text(&msg);
                    toast_c.add_toast(adw::Toast::new("Sync ready"));
                });
            }
            Err(err) => {
                let msg = format!("Auth failed: {err}");
                glib::MainContext::default().invoke(move || {
                    status_c.set_text(&msg);
                });
            }
        }
    });

    // Example: periodic adaptive sync tick (replace with SyncEngine).
    let runtime_c = runtime.clone();
    glib::timeout_add_seconds_local(90, move || {
        let rt = runtime_c.clone();
        rt.spawn(async {
            let _ = run_incremental_sync().await;
        });
        glib::ControlFlow::Continue
    });

    window.present();
}

/// Placeholder: PKCE + loopback OAuth, then load tokens from Secret Service.
async fn bootstrap_session() -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    // 1. Try libsecret for existing refresh_token
    // 2. Else start loopback listener, open system browser, exchange code
    // 3. Return account email from userinfo
    Ok("user@example.com".into())
}

/// Placeholder: Calendar syncToken + Tasks updatedMin against SQLite.
async fn run_incremental_sync() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    Ok(())
}
