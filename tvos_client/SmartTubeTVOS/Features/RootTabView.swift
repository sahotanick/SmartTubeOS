import SwiftUI

struct RootTabView: View {
    @EnvironmentObject private var appState: AppState

    var body: some View {
        TabView {
            NavigationStack {
                FeedScreen(title: "Home", requiresAuth: false) { token in
                    try await appState.api.fetchHome(continuationToken: token)
                }
            }
            .tabItem { Label("Home", systemImage: "house") }

            NavigationStack {
                SearchScreen()
            }
            .tabItem { Label("Search", systemImage: "magnifyingglass") }

            NavigationStack {
                FeedScreen(title: "Subscriptions", requiresAuth: true) { token in
                    try await appState.api.fetchSubscriptions(continuationToken: token)
                }
            }
            .tabItem { Label("Subscriptions", systemImage: "rectangle.stack.badge.person.crop") }

            NavigationStack {
                FeedScreen(title: "History", requiresAuth: true) { token in
                    try await appState.api.fetchHistory(continuationToken: token)
                }
            }
            .tabItem { Label("History", systemImage: "clock.arrow.circlepath") }

            NavigationStack {
                SettingsScreen()
            }
            .tabItem { Label("Settings", systemImage: "gearshape") }
        }
    }
}
