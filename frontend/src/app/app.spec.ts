import { App } from './app';

describe('App', () => {
  it('should expose the root component class', () => {
    const app = new App();

    expect(app).toBeTruthy();
  });
});
