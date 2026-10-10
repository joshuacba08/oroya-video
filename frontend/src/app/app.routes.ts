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
        title: 'Oroya Video - Dashboard',
      },
      {
        path: 'projects',
        loadComponent: () =>
          import('./features/projects/projects.page').then((m) => m.ProjectsPage),
        title: 'Oroya Video - Projects',
      },
      {
        path: 'projects/:id',
        loadComponent: () =>
          import('./features/workspace/workspace.page').then((m) => m.WorkspacePage),
        title: 'Oroya Video - Workspace',
      },
      {
        path: 'queue',
        loadComponent: () =>
          import('./features/queue/queue.page').then((m) => m.QueuePage),
        title: 'Oroya Video - Processing Queue',
      },
      {
        path: 'models',
        loadComponent: () =>
          import('./features/models/models.page').then((m) => m.ModelsPage),
        title: 'Oroya Video - Models',
      },
      {
        path: 'exports',
        loadComponent: () =>
          import('./features/exports/exports.page').then((m) => m.ExportsPage),
        title: 'Oroya Video - Exports',
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./features/settings/settings.page').then((m) => m.SettingsPage),
        title: 'Oroya Video - Settings',
      },
      {
        path: 'setup',
        loadComponent: () =>
          import('./features/setup/setup.page').then((m) => m.SetupPage),
        title: 'Oroya Video - Setup',
      },
    ],
  },
  {
    path: '**',
    redirectTo: 'dashboard',
  },
];
