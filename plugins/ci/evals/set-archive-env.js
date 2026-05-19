module.exports = async function ({ test }) {
  const archiveDir = test.vars?.archive_dir;
  if (archiveDir) {
    process.env.EVAL_ARCHIVES_DIR = archiveDir;
  }
};
