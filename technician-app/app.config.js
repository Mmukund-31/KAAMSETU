// Extends app.json. Android blocks plain-HTTP traffic in builds by default; a demo build that talks to a laptop on
// the LAN (http://<ip>:8001) needs it allowed. Only builds made with KAAMSETU_ALLOW_HTTP=1 (the "preview" profile
// in eas.json) get the exception; production builds must use an HTTPS backend.
module.exports = ({ config }) => {
  if (process.env.KAAMSETU_ALLOW_HTTP !== "1") return config;
  return {
    ...config,
    plugins: [...(config.plugins ?? []), ["expo-build-properties", { android: { usesCleartextTraffic: true } }]],
  };
};
