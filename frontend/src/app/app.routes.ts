import { Routes } from '@angular/router';

import { AppShellComponent } from './layout/app-shell.component';

export const routes: Routes = [
  {
    path: '',
    component: AppShellComponent,
    children: [
      {
        path: '',
        pathMatch: 'full',
        redirectTo: 'dashboard',
      },
      {
        path: 'dashboard',
        loadComponent: () =>
          import('./features/dashboard/dashboard.page').then((m) => m.DashboardPage),
        title: 'nav.dashboard',
      },
      {
        path: 'projects',
        loadComponent: () =>
          import('./features/projects/projects.page').then((m) => m.ProjectsPage),
        title: 'nav.projects',
      },
      {
        path: 'projects/:id',
        loadComponent: () =>
          import('./features/workspace/workspace.page').then((m) => m.WorkspacePage),
        title: 'nav.workspace',
      },
      {
        path: 'queue',
        loadComponent: () =>
          import('./features/queue/queue.page').then((m) => m.QueuePage),
        title: 'nav.queue',
      },
      {
        path: 'models',
        loadComponent: () =>
          import('./features/models/models.page').then((m) => m.ModelsPage),
        title: 'nav.models',
      },
      {
        path: 'exports',
        loadComponent: () =>
          import('./features/exports/exports.page').then((m) => m.ExportsPage),
        title: 'nav.exports',
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/settings.page').then((m) => m.SettingsPage),
        title: 'nav.settings',
      },
      {
        path: 'setup',
        loadComponent: () =>
          import('./features/setup/setup.page').then((m) => m.SetupPage),
        title: 'nav.setup',
      },
    ],
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
