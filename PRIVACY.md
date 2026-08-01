# Privacy Notes

The MobileMem project page is a static site. It does not provide accounts, accept form submissions,
or store visitor input in browser storage.

## Page-view counter

When the page is served over HTTP or HTTPS, `assets/web/js/main.js` loads the third-party Busuanzi
counter from:

```text
https://busuanzi.ibruce.info/busuanzi/2.3/busuanzi.pure.mini.js
```

That service receives a normal web request and may process request metadata, such as the visitor's
IP address, user agent, referring page, and requested page, in order to produce the displayed page
count. Its collection, retention, and security practices are controlled by the service provider.
The counter is not loaded when the page is opened directly from the local filesystem.

## Published research samples

Bundled images and dialogue trajectories are publicly downloadable, including samples that are not
currently visible on screen. Their file groups and image-integrity manifest are documented in
[ASSETS.md](ASSETS.md).
